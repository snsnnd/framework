/**
 * @file    ramp.c
 * @brief   斜坡控制器实现 —— 限制输出变化的升降速率
 *
 * 由 EFW_ENABLE_ALGO_RAMP 宏控制编译。
 *
 * =========================================================================
 * 算法详情
 * =========================================================================
 *
 *   ① 计算差距：delta = target - value
 *   ② 计算本周期限速步长：limit = rate × dt
 *      rate 取 rise_rate (delta≥0) 或 fall_rate (delta<0)
 *   ③ 钳位 delta：|delta| ≤ limit（不超限速）
 *   ④ 更新 value：value += delta
 *
 *   为什么分离 rise_rate 和 fall_rate？
 *     很多场景下加速可以快但减速要慢：
 *       - 电机加速 → 允许快速响应
 *       - 电机制动 → 需要平滑减速避免机械冲击
 *       - LED 亮起 → 可以很快
 *       - LED 熄灭 → 可以很慢 (渐隐效果)
 *
 * =========================================================================
 * 参数调节
 * =========================================================================
 *
 *   rise_rate/fall_rate 的物理含义是"每秒最多变化多少"。
 *   单位取决于 value 的含义：
 *     - PWM 占空比 (0~100)：rate=50 意味着每秒最多变 50%
 *     - 速度 (m/s)：rate=2.0 意味着每秒最多加速 2m/s
 *
 *   建议从较小的 rate 开始测试，逐步增大到响应速度可接受。
 *   rate 设为 0 或负数 → run 返回 EFW_ERR_INVALID (无效配置)。
 *   efw_ramp_reset() 可以跳过斜坡直接跳到目标值。
 */

#include "efw/core/config.h"
#include "efw/algorithm/control/ramp.h"

#if EFW_ENABLE_ALGO_RAMP  /**< 编译开关 */

/**
 * @brief 重置斜坡值 —— 直接跳到指定值 (不经过斜坡)
 *
 * 用于初始化时设置起始值，避免从 0 到目标值的冗长斜坡过程。
 */
void efw_ramp_reset(efw_ramp_t *ramp, float value) {
    if (ramp) ramp->value = value;      /* 直接赋值，跳过斜坡限速 */
}

/**
 * @brief 执行一次斜坡计算 (可注册为 algo_ops.run)
 *
 * 算法 4 步：
 *   ① delta = target - value          — 差距
 *   ② limit = rate × dt                — 本周期最大步长
 *      rate 根据 delta 符号取 rise_rate 或 fall_rate
 *   ③ 钳位 delta 到 ±limit 范围        — 不超过限速
 *   ④ value += delta                   — 更新状态
 *
 * @param ctx 指向 efw_ramp_t
 * @param in  指向 efw_ramp_input_t (target + dt)
 * @param out 指向 float (斜坡后输出)
 * @return EFW_OK / EFW_ERR_INVALID
 */
efw_status_t efw_ramp_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    efw_ramp_t *ramp = (efw_ramp_t *)ctx;
    const efw_ramp_input_t *input = (const efw_ramp_input_t *)in;
    float *result = (float *)out;
    float delta;
    float limit;
    if (!ramp || !input || !result) return EFW_ERR_INVALID;
    if (in_size < sizeof(efw_ramp_input_t) || out_size < sizeof(float)) return EFW_ERR_RANGE;

    /* 参数校验 */
    if (!ramp || !input || !result || input->dt <= 0.0f) return EFW_ERR_INVALID;

    /* ① 差距 = 目标 - 当前 */
    delta = input->target - ramp->value;

    /* ② 本周期限速步长：上升用 rise_rate，下降用 fall_rate */
    limit = (delta >= 0.0f ? ramp->rise_rate : ramp->fall_rate) * input->dt;

    /* rate 不能为负 (无效配置) */
    if (limit < 0.0f) return EFW_ERR_INVALID;

    /* ③ 钳位 delta 到 ±limit 范围 (不超过限速) */
    if (delta > limit) delta = limit;           /* 超过上升限速 → 钳位 */
    if (delta < -limit) delta = -limit;          /* 超过下降限速 → 钳位 */

    /* ④ 更新当前值 */
    ramp->value += delta;
    *result = ramp->value;                       /* 输出斜坡后结果 */
    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_RAMP */
