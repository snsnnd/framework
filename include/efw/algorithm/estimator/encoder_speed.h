/**
 * @file    encoder_speed.h
 * @brief   编码器速度估算器 —— 从脉冲计数推算转速/线速度
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 *   编码器输出脉冲计数 (int32_t count)，速度估算器通过两次采样的
 *   计数差除以时间间隔来计算速度。
 *
 * 【公式】
 *   diff = count(t) - count(t-1)           — 脉冲数变化量
 *   speed = (diff / pulses_per_unit) / dt   — 速度 = 物理量变化 / 时间
 *
 *   pulses_per_unit 的含义取决于编码器类型：
 *     - 测转速：pulses_per_unit = 编码器线数 × 4 (4 倍频) → speed 单位 = 转/秒
 *     - 测线速度：pulses_per_unit = 每米脉冲数 → speed 单位 = m/s
 *     - 测角度：pulses_per_unit = 每度脉冲数 → speed 单位 = °/s
 *
 * 【初始化】
 *   首次调用时自动记录初始 count，返回 speed=0。
 *   后续调用正常计算差值。
 *
 * 【参数调节】
 *   pulses_per_unit — 这是唯一需要设置的参数。
 *     例如：编码器 1000 线，4 倍频解码 → 4000 脉冲/转
 *     设置 pulses_per_unit = 4000 → speed 输出单位 = 转/秒
 *   dt — 控制周期，越短速度噪声越大 (差值/小时间 = 放大噪声)
 *        推荐配合低通滤波使用：编码器速度 → 低通滤波 → PID
 */

#ifndef EFW_ALGORITHM_ENCODER_SPEED_H
#define EFW_ALGORITHM_ENCODER_SPEED_H

#include "efw/core/common.h"

/**
 * @brief 编码器速度估算器状态
 *
 * @field prev_count      上一次脉冲计数 [内部状态]
 * @field pulses_per_unit 每物理单位的脉冲数 (如 4000=每转 4000 脉冲)
 *                        必须 > 0，为 0 时 run 返回错误
 * @field initialized     是否已初始化 [内部状态]
 */
typedef struct {
    int32_t prev_count;         /**< [内部] 上次脉冲计数 */
    float pulses_per_unit;      /**< 每单位脉冲数 (必须 > 0) */
    uint8_t initialized;        /**< [内部] 首次调用标记 */
} efw_encoder_speed_t;

/**
 * @brief 编码器速度估算器输入
 * @field count 当前脉冲计数值
 * @field dt    距上次调用的时间间隔 (秒)，必须 > 0
 */
typedef struct {
    int32_t count;      /**< 当前脉冲计数 */
    float dt;           /**< 时间间隔 (秒) */
} efw_encoder_speed_input_t;

/**
 * @brief 执行一次速度估算 (可注册为 algo_ops.run)
 *
 * @param ctx 指向 efw_encoder_speed_t
 * @param in  指向 efw_encoder_speed_input_t
 * @param out 指向 float (速度值写入此处)
 * @return EFW_OK / EFW_ERR_INVALID (参数非法, dt≤0, pulses_per_unit=0)
 */
efw_status_t efw_encoder_speed_run(void *ctx, const void *in, void *out);

#endif
