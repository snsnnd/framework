/**
 * @file    pid.c
 * @brief   PID 控制器完整实现 (位置式并行 PID + 前馈 + 抗积分饱和)
 *
 * 本文件由 EFW_ENABLE_ALGO_PID 宏控制编译。
 *
 * =========================================================================
 * 算法步骤（每次 efw_pid_run 调用）
 * =========================================================================
 *
 *   ① 类型转换：ctx→pid, in→input, out→output
 *   ② 参数校验：ctx/in/out 非 NULL、dt > 0
 *   ③ 误差：error = setpoint - feedback
 *   ④ 积分 (含限幅)：integral = clamp(integral + error×dt, integral_min, integral_max)
 *      仅当 integral_min < integral_max 时有效，否则不钳位
 *   ⑤ 微分：derivative = (error - prev_error) / dt  ← 后向差分
 *   ⑥ 前馈：feedforward = input->feedforward + Kff × setpoint
 *      前馈是"开环"分量——不依赖反馈，直接给出预期控制量
 *   ⑦ PID+前馈综合：
 *       value_no_i = feedforward + Kp·error + Kd·derivative   ← 不含积分项
 *       value = value_no_i + Ki·integral                     ← 加上积分
 *   ⑧ 输出限幅：clamped = clamp(value, out_min, out_max)
 *   ⑨ 抗积分饱和 (anti-windup)：若输出被钳位且 anti_windup=1：
 *       回算积分 → integral = (clamped - value_no_i) / Ki
 *       再对 integral 做限幅钳位
 *       含义：只累积"真正生效"的那部分——被钳掉的不累积
 *   ⑩ 保存状态 + 写回结果
 *
 * =========================================================================
 * 调参指南
 * =========================================================================
 *
 *   标准 PID (Kff=0, anti_windup=0)：
 *     第1步：Ki=0, Kd=0 → 调 Kp 到 10%~20% 超调
 *     第2步：加入 Ki (从 0.01×Kp) → 调至稳态误差消失
 *     第3步：加入 Kd (从 0.01×Kp) → 调至超调量满意
 *
 *   启用前馈 (有先验模型时)：
 *     第4步：设置 Kff (如已知 "2m/s≈40%PWM" → Kff=40/2=20)
 *           观察响应速度是否提升；output.feedforward 查看前馈贡献
 *
 *   启用抗积分饱和 (有输出限幅时推荐)：
 *     第5步：anti_windup=1, integral_min=-out_max/Ki, integral_max=out_max/Ki
 *           测试大幅阶跃（如 0→100%）是否还会有长时间超调
 *
 *   常见问题：
 *     - 振荡：Kp 太大 或 Kd 太小 或 anti_windup 关闭但积分饱和
 *     - 响应慢：Kp/Ki 太小 或 缺少前馈 (加 Kff)
 *     - 超调严重：Kd 太小 或 Ki 太大 或 积分限幅不合理
 *     - 高频抖动：Kd 太大 (减 Kd 或先滤波)
 *     - 稳态有偏差：Ki 太小 或 integral_min/max 钳住了积分
 */

#include "efw/core/config.h"
#include "efw/algorithm/control/pid.h"

#if EFW_ENABLE_ALGO_PID

/**
 * @brief 浮点数钳位 —— 将 value 限制在 [min_value, max_value] 范围
 * 当 min≥max (异常配置) 时返回原值（不做钳位）
 */
static float clamp_float(float value, float min_value, float max_value) {
    if (min_value < max_value) {
        if (value < min_value) return min_value;
        if (value > max_value) return max_value;
    }
    return value;
}

/**
 * @brief 检查钳位是否有效 —— min < max 时为真
 * 用于 anti_windup 的前置条件判断
 */
static int clamp_enabled(float min_value, float max_value) {
    return min_value < max_value;
}

/**
 * @brief 重置 PID 状态 —— 清零积分累积和上一次误差
 *
 * ★ 必须在设定值大幅跳变（如 2m/s→5m/s）、系统重启、手动切回自动时调用。
 * 不调用会导致 integral windup（积分饱和）：旧的积分值产生冲激输出。
 */
void efw_pid_reset(efw_pid_t *pid) {
    if (!pid) return;
    pid->integral = 0.0f;
    pid->prev_error = 0.0f;
}

/**
 * @brief 执行一次 PID 计算 (核心算法，可注册为 algo_ops.run)
 *
 * ★ 完整公式：
 *   error = setpoint - feedback
 *   integral = clamp(integral + error×dt, integral_min, integral_max)
 *   derivative = (error - prev_error) / dt
 *   feedforward = input->feedforward + Kff × setpoint
 *   value_no_i = feedforward + Kp×error + Kd×derivative      ← P+D+FF
 *   value = value_no_i + Ki×integral                         ← +I
 *   clamped = clamp(value, out_min, out_max)
 *   {anti-windup} if clamped≠value: integral = (clamped - value_no_i)/Ki
 *
 * @param ctx 指向 efw_pid_t (所有PID参数和内部状态)
 * @param in  指向 efw_pid_input_t (setpoint/feedback/dt/feedforward)
 * @param out 指向 efw_pid_output_t (output/error/feedforward 写回)
 * @return EFW_OK / EFW_ERR_INVALID
 */
efw_status_t efw_pid_run(void *ctx, const void *in, void *out) {
    /* Step 1: void* → 具体类型 */
    efw_pid_t *pid = (efw_pid_t *)ctx;
    const efw_pid_input_t *input = (const efw_pid_input_t *)in;
    efw_pid_output_t *output = (efw_pid_output_t *)out;
    float error;        /* 本次误差 = setpoint - feedback */
    float derivative;   /* 误差变化率 = (error - prev_error) / dt */
    float integral;     /* 本次积分值 (含限幅) */
    float feedforward;  /* 总前馈 = input前馈 + Kff×setpoint */
    float value_no_i;   /* P + D + FF 的合计 (不含积分，供 anti-windup 回算用) */
    float value;        /* value_no_i + Ki×integral (限幅前总输出) */
    float clamped;      /* 限幅后的最终输出值 */

    /* Step 2: 参数校验 */
    if (!pid || !input || !output || input->dt <= 0.0f) return EFW_ERR_INVALID;

    /* Step 3: 误差 = 目标 - 实际 */
    error = input->setpoint - input->feedback;

    /* Step 4: 积分累积 (矩形法)，可选积分限幅 */
    integral = pid->integral + error * input->dt;
    integral = clamp_float(integral, pid->integral_min, pid->integral_max);
    /* 若 integral_min ≥ integral_max → clamp_float 返回原值 → 不限幅 */

    /* Step 5: 微分 = Δerror / Δt (后向差分) */
    derivative = (error - pid->prev_error) / input->dt;

    /* Step 6: 前馈 = 动态前馈 + 静态前馈 (Kff × setpoint) */
    feedforward = input->feedforward + pid->kff * input->setpoint;
    /* input->feedforward：每次调用可变的动态前馈 (如弯道预判补偿)
     * Kff × setpoint      ：与设定值成正比的静态前馈 (如 "2m/s≈40%PWM") */

    /* Step 7: PID+前馈综合 */
    value_no_i = feedforward + pid->kp * error + pid->kd * derivative;
    /* value_no_i = FF + P + D (不含 I 项，供 anti_windup 回算) */
    value = value_no_i + pid->ki * integral;
    /* value = FF + P + I + D */

    /* Step 8: 输出限幅 */
    clamped = clamp_float(value, pid->out_min, pid->out_max);

    /* Step 9: ★ 抗积分饱和 (Anti-Windup)
     * 仅当以下条件全部满足时生效：
     *   ① anti_windup 开关打开
     *   ② Ki ≠ 0 (否则回算公式除零)
     *   ③ 限幅有效 (out_min < out_max)
     *   ④ 输出确实被钳位了 (clamped ≠ value)
     *
     * 原理：反推"产生钳位输出的积分应该是多少" → integral = (clamped - value_no_i) / Ki
     * 这样下次调用时积分只基于"真正生效"的部分累积，被钳掉的部分不积累。
     */
    if (pid->anti_windup && pid->ki != 0.0f &&
        clamp_enabled(pid->out_min, pid->out_max) && clamped != value) {
        /* 回算积分：如果 clamped = value_no_i + Ki × new_integral，
         *          则 new_integral = (clamped - value_no_i) / Ki */
        integral = (clamped - value_no_i) / pid->ki;
        /* 回算后的积分再做一次限幅，防止极端情况 */
        integral = clamp_float(integral, pid->integral_min, pid->integral_max);
    }

    /* Step 10: 保存状态 + 写回结果 */
    pid->integral = integral;           /* 更新积分 (可能被 anti-windup 修正过) */
    pid->prev_error = error;            /* 保存误差供下次微分 */
    output->output = clamped;           /* 限幅后的控制量 → 驱动执行器 */
    output->error = error;              /* 原始误差 → 供监控 */
    output->feedforward = feedforward;  /* 总前馈量 → 供调试 */

    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_PID */
