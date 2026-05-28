/**
 * @file    pid.h
 * @brief   PID 控制器 —— 位置式并行 PID + 前馈 + 抗积分饱和
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 * PID 全称 Proportional-Integral-Derivative（比例-积分-微分），是自动控制
 * 领域最经典、最通用的反馈控制算法。
 *
 * 本实现扩展了标准 PID，额外支持：
 *   ① 前馈控制 (Feedforward)     — 按设定值直接给出开环补偿，绕过反馈延迟
 *   ② 积分限幅 (Integral Clamping) — 限制积分项的最大/最小累积值
 *   ③ 抗积分饱和 (Anti-Windup)    — 输出被钳位时自动回算积分，防止失控
 *
 * 【数学公式 (完整形式)】
 *   error       = setpoint - feedback
 *   integral    = clamp(integral + error×dt, integral_min, integral_max)
 *   derivative  = (error - prev_error) / dt
 *   feedforward = input->feedforward + Kff × setpoint
 *   output      = feedforward + Kp·error + Ki·integral + Kd·derivative
 *   output      = clamp(output, out_min, out_max)
 *   {anti-windup} 若输出被钳位：integral = (output - value_no_i) / Ki
 *
 * 【四项的物理意义——以"小车电机调速"为例 (setpoint=2m/s)】
 *
 *   P (比例) — 对"当前"误差的即时响应
 *     小车当前速度 0m/s，error=2，Kp=1.5 → P项贡献 3.0 (如 30% PWM)
 *     作用：快速缩小误差，Kp 越大响应越快，但过大会导致超调振荡
 *
 *   I (积分) — 对"历史"误差的累积补偿
 *     当 P 项将速度稳定在 1.9m/s 后，还剩 0.1 的稳态误差
 *     积分项不断累积这 0.1×dt，最终产生额外输出补上缺口 → 精确到 2.0
 *     作用：消除稳态误差。Ki 过大会导致超调和积分饱和
 *
 *   D (微分) — 对"未来"趋势的预测阻尼
 *     速度从 0 快速逼近 2.0 时，error 减小得很快，de/dt 为负
 *     D 项产生"刹车"效果，防止冲过头
 *     作用：抑制超调，提供阻尼。Kd 过大会放大传感器高频噪声
 *
 *   FF (前馈) — 对"已知"扰动的开环补偿
 *     如果你事先知道"车速 2m/s 大约需要 40% PWM"，可以直接加 40% 前馈
 *     PID 只需要修正剩余的误差部分，响应速度大幅提升
 *     作用：加快响应，减少 PID 的负担。但不参与闭环校正
 *     Kff × setpoint = 静态前馈（跟设定值成正比）
 *     input->feedforward = 动态前馈（每次调用可不同，如弯道预判补偿）
 *
 * =========================================================================
 * 抗积分饱和 (Anti-Windup) 原理
 * =========================================================================
 *
 *   当 PID 输出超出限幅范围被钳位时，如果积分项继续累积，会导致
 *   "积分饱和"：一旦误差反向，积分需要很长时间才能"退出来"，
 *   表现为严重超调和长时间振荡。
 *
 *   抗积分饱和的核心思想：
 *     当输出被钳位时，回算积分：integral = (clamped_output - value_no_i) / Ki
 *     这等价于"只累积真正生效的那部分误差"——钳位部分不累积。
 *
 *   开启方式：设置 anti_windup = 1。
 *   前提条件：Ki ≠ 0 且 out_min < out_max（限幅有效）。
 *   如果 Ki=0（纯 PD 控制），anti_windup 无意义，自动跳过。
 *
 * =========================================================================
 * 积分限幅 (integral_min / integral_max)
 * =========================================================================
 *
 *   积分项可能无限累积（比如长时间达不到目标），通过 integral_min/max
 *   限制积分项的范围。仅当 integral_min < integral_max 时生效。
 *
 *   典型设置：
 *     integral_min = -out_max / Ki  (如 -100/0.2 = -500)
 *     integral_max =  out_max / Ki  (如  100/0.2 =  500)
 *   如果不使用积分限幅，设置 integral_min = integral_max = 0 即可。
 *
 * =========================================================================
 * 参数调节方法
 * =========================================================================
 *
 *   方法一：Ziegler-Nichols 临界比例度法
 *     ① 设 Ki=0, Kd=0, Kff=0，逐步增大 Kp 直到系统等幅振荡
 *     ② 记下临界增益 Ku 和振荡周期 Tu
 *     ③ PID：Kp=0.6Ku, Ki=1.2Ku/Tu, Kd=0.075Ku×Tu
 *
 *   方法二：手动试凑法 (推荐)
 *     第1步：Kff=0, Ki=0, Kd=0 → 调 Kp 到轻微超调 (~10%)
 *     第2步：加入 Ki (从 0.01×Kp 开始) → 调到稳态误差消失
 *     第3步：加入 Kd (从 0.01×Kp 开始) → 调到超调量满足
 *     第4步：加入 Kff (如有前馈模型) → 减少 PID 负担
 *     第5步：开启 anti_windup=1，设置合理的 integral_min/max
 *
 *   口诀：比例看响应速度，积分看稳态精度，微分看阻尼程度，前馈看先验知识
 *
 * 【常见问题及对策】
 *   输出持续振荡       → Kp 太大 (减) 或 Kd 太小 (加)
 *   响应很慢           → Kp 太小 (加) 或 Ki 太小 (加) 或加 Kff
 *   超调严重           → 加 Kd (阻尼) 或减 Ki (降积分) 或开启 anti_windup
 *   电机高频啸叫       → Kd 太大 (减 Kd) 或先做滤波
 *   长时间偏差不消失   → 检查 anti_windup 和 integral_min/max 是否合理
 *   阶跃响应慢但稳态准 → 加 Kff (前馈直接给开环量，PID 只修误差)
 * =========================================================================
 */

#ifndef EFW_ALGORITHM_PID_H
#define EFW_ALGORITHM_PID_H

#include "efw/core/common.h"

/**
 * @brief PID 控制器状态结构体 (每个 PID 实例需要唯一一个)
 *
 * 此结构体保存 PID 的"历史记忆"——积分累积值和上一次误差。
 * 每次调用 efw_pid_run 会读取并更新这些内部状态。
 */
typedef struct {
    float kp;           /**< 比例系数 P：对当前误差的增益。越大响应越快，过大会振荡 */
    float ki;           /**< 积分系数 I：对历史累积误差的增益。消除稳态误差，过大会超调 */
    float kd;           /**< 微分系数 D：对误差变化率的增益。提供阻尼预测，过大会放大噪声 */
    float kff;          /**< 前馈系数 FF：按 setpoint 直接给出开环补偿。
                             Kff × setpoint = 静态前馈量。设为 0 表示不使用前馈。
                             例如已知 "2m/s ≈ 40% PWM" → Kff = 40/2 = 20 */
    float integral;     /**< [内部状态] 积分累积值 = Σ(error × dt)，被 integral_min/max 钳位 */
    float prev_error;   /**< [内部状态] 上一次误差值，用于计算微分项 de/dt */
    float integral_min; /**< 积分下限：仅 integral_min < integral_max 时生效。
                             限制积分不会"负得太离谱"。
                             设 integral_min = integral_max = 0 可禁用积分限幅 */
    float integral_max; /**< 积分上限：限制积分不会"正得太离谱" */
    float out_min;      /**< 输出下限：output 允许的最小值 (如 PWM 0%，电机反转 -100) */
    float out_max;      /**< 输出上限：output 允许的最大值 (如 PWM 100%，电机正转 +100) */
    uint8_t anti_windup;/**< 抗积分饱和开关：1=输出被钳位时回算积分；0=普通积分累积。
                             需要 Ki≠0 和 out_min<out_max 同时成立才生效 */
} efw_pid_t;

/**
 * @brief PID 单次输入 —— 调用方每次 run 时填充
 *
 * @field setpoint    设定值/目标值 (如期望速度 2.0 m/s, 期望角度 0°)
 * @field feedback    反馈值/实际测量值 (如编码器实测速度 1.8 m/s, IMU 实测角度 3°)
 * @field dt          距上次调用 PID 的时间间隔 (单位：秒)
 *                    例如控制周期 10ms → dt=0.01f, 1ms → dt=0.001f
 *                    必须 > 0，否则 efw_pid_run 返回 EFW_ERR_INVALID
 * @field feedforward  动态前馈量 (每次调用可不同)，直接叠加到输出上。
 *                     与 Kff×setpoint 相加后构成总前馈。
 *                     典型用途：弯道预判补偿、摩擦补偿。默认填 0。
 */
typedef struct {
    float setpoint;     /**< 设定值 (目标) */
    float feedback;     /**< 反馈值 (实测) */
    float dt;           /**< 时间间隔 (秒)，必须 > 0 */
    float feedforward;  /**< 动态前馈 (可每次调用变化)，默认填 0 */
} efw_pid_input_t;

/**
 * @brief PID 单次输出 —— efw_pid_run 将结果写入此处
 *
 * @field output      控制器输出 (已钳位到 [out_min, out_max])
 * @field error       当前误差 (setpoint - feedback)，供上层监控/日志
 * @field feedforward  本次实际使用的总前馈量 (input->feedforward + Kff×setpoint)
 *                     用于调试和监控前馈的贡献大小
 */
typedef struct {
    float output;       /**< 控制器输出 (已限幅) */
    float error;        /**< 当前误差 (供监控用) */
    float feedforward;  /**< 本次实际总前馈量 */
} efw_pid_output_t;

void efw_pid_reset(efw_pid_t *pid);
efw_status_t efw_pid_run(void *ctx, const void *in, void *out);

#endif
