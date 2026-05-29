/**
 * @file    encoder_speed.c
 * @brief   编码器速度估算器实现 —— 脉冲计数差分求速度
 *
 * 由 EFW_ENABLE_ALGO_ENCODER_SPEED 宏控制编译。
 *
 * =========================================================================
 * 算法详情
 * =========================================================================
 *
 *   diff = count(t) - count(t-1)
 *   speed = (diff / pulses_per_unit) / dt
 *
 *   首次调用：记录 count 但不计算 (无法做差分)，返回 speed=0。
 *   后续调用：正常计算差分速度。
 *
 * =========================================================================
 * 注意事项
 * =========================================================================
 *
 *   ① 脉冲计数溢出：int32_t 范围约 ±21 亿。如果编码器持续单向旋转，
 *      计数会溢出。使用前应确保编码器硬件或 HAL 层处理了溢出 (如自动回绕)。
 *      本实现直接做减法——如果 count 在溢出边界回绕，diff 会不连续。
 *
 *   ② 低速噪声：低速时相邻两次 count 差为 0 或 1，
 *      speed 分辨率极低 (±1/dt 的整数倍)。推荐配合低通滤波使用。
 *
 *   ③ pulses_per_unit 的确定：
 *      - 增量编码器 1000 线 + 4 倍频 → 4000 脉冲/转
 *      - 设 pulses_per_unit=4000 → speed 单位=转/秒
 *      - 要 m/s，还需乘以轮周长：speed_mps = speed_rps × π × 轮径
 *        建议在外层算法中做此换算。
 */

#include "efw/core/config.h"
#include "efw/algorithm/estimator/encoder_speed.h"

#if EFW_ENABLE_ALGO_ENCODER_SPEED  /**< 编译开关 */

/**
 * @brief 执行一次速度估算 (可注册为 algo_ops.run)
 *
 * 首次调用记录初始 count，返回 speed=0。
 * 后续调用：speed = (count_diff / pulses_per_unit) / dt
 *
 * @param ctx 指向 efw_encoder_speed_t
 * @param in  指向 efw_encoder_speed_input_t (count + dt)
 * @param out 指向 float (速度值写入)
 * @return EFW_OK / EFW_ERR_INVALID
 */
efw_status_t efw_encoder_speed_run(void *ctx, const void *in, void *out) {
    efw_encoder_speed_t *est = (efw_encoder_speed_t *)ctx;             /* ctx → 估算器 */
    const efw_encoder_speed_input_t *input = (const efw_encoder_speed_input_t *)in;  /* 输入 */
    float *speed = (float *)out;                                        /* 输出 */
    int32_t diff;           /* 脉冲计数变化量 */

    /* 参数校验：指针非空 + dt>0 + pulses_per_unit 已设置 */
    if (!est || !input || !speed || input->dt <= 0.0f || est->pulses_per_unit == 0.0f)
        return EFW_ERR_INVALID;

    /* 首次调用 → 记录初始 count，不计算速度 */
    if (!est->initialized) {
        est->prev_count = input->count;     /* 记录初始脉冲值 */
        est->initialized = 1;               /* 标记已初始化 */
        *speed = 0.0f;                      /* 首次返回 0 (没有差分基准) */
        return EFW_OK;
    }

    /* 计算脉冲差 + 更新上次值 */
    diff = input->count - est->prev_count;  /* 两次采样间的脉冲变化量 */
    est->prev_count = input->count;         /* 保存供下次差分 */

    /* 速度 = (脉冲差 / 每单位脉冲数) / 时间 */
    *speed = ((float)diff / est->pulses_per_unit) / input->dt;

    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_ENCODER_SPEED */
