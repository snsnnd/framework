/**
 * @file    low_pass.h
 * @brief   一阶低通滤波器 (Exponential Moving Average / IIR 低通)
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 *   一阶低通滤波器是最简单的 IIR (无限冲激响应) 数字滤波器。
 *   它用指数加权的方式平滑输入信号，本质上是一个"遗忘因子"机制。
 *
 * 【公式】
 *   state(t) = state(t-1) + α × (sample - state(t-1))
 *
 *   展开后等价于：
 *   state(t) = α × sample + (1-α) × state(t-1)
 *
 *   state = 滤波后的输出 (状态变量)
 *   sample = 当前原始采样值
 *   α (alpha) = 平滑系数，范围 [0, 1]
 *
 * 【物理含义】
 *   α = 1.0  → state = sample (无滤波，完全信任新值) → 等同于直通
 *   α = 0.0  → state = state (完全滤波，忽略新值)   → 输出冻结
 *   α = 0.1  → 10% 新值 + 90% 旧值 → 强平滑，但响应滞后
 *   α = 0.5  → 等权重 → 中度平滑
 *
 * 【vs 滑动均值】
 *   低通滤波：O(1) 计算量，仅需 1 个状态变量，无 buffer
 *            适合信号连续变化、对历史不要求等权的场景
 *   滑动均值：需要 N 个 buffer，但过去 N 个点等权
 *            适合需要精确窗口平均的场景
 *
 * 【截止频率估算】
 *   对于固定采样周期 dt：
 *     截止频率 fc ≈ α / (2π × dt)
 *     例如 α=0.1, dt=0.01s → fc ≈ 0.1/(2π×0.01) ≈ 1.6 Hz
 *     实际使用时建议通过实验调节 α，不必精确计算 fc。
 *
 * 【参数调节】
 *   α 越大 → 响应越快，平滑越弱 (高频信号，如 IMU 角速度用 α=0.3~0.5)
 *   α 越小 → 响应越慢，平滑越强 (低频信号，如温度用 α=0.01~0.05)
 *   首次调用时自动用第一个采样值初始化 state (避免从 0 起步的阶跃)
 */

#ifndef EFW_ALGORITHM_LOW_PASS_H
#define EFW_ALGORITHM_LOW_PASS_H

#include "efw/core/common.h"

/**
 * @brief 一阶低通滤波器状态
 *
 * @field alpha       平滑系数 [0, 1]。1=无滤波, 0=不更新。超出范围 run 返回错误
 * @field state       当前滤波输出值 [内部状态]
 * @field initialized 是否已初始化标记 [内部状态]。首次 run 时自动用第一个 sample 初始化
 */
typedef struct {
    float alpha;        /**< 平滑系数 (0~1) */
    float state;        /**< [内部] 当前滤波输出 */
    uint8_t initialized;/**< [内部] 是否已初始化 */
} efw_low_pass_t;

/**
 * @brief 重置滤波器 —— 将 state 设为指定值并标记已初始化
 * @param filter 滤波器实例
 * @param value  初始值 (如传感器当前读数)
 */
void efw_low_pass_reset(efw_low_pass_t *filter, float value);

/**
 * @brief 执行一次低通滤波 (可注册为 algo_ops.run)
 *
 * @param ctx 指向 efw_low_pass_t
 * @param in  指向 float (新采样值)
 * @param out 指向 float (滤波后输出)
 * @return EFW_OK / EFW_ERR_INVALID (参数非法或 alpha 超出 [0,1])
 */
efw_status_t efw_low_pass_run(void *ctx, const void *in, void *out);

#endif
