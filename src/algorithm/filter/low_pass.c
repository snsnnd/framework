/**
 * @file    low_pass.c
 * @brief   一阶低通滤波器实现 (指数移动平均 / IIR 低通)
 *
 * 由 EFW_ENABLE_ALGO_LOW_PASS 宏控制编译。
 *
 * =========================================================================
 * 算法详情
 * =========================================================================
 *
 *   state += α × (sample - state)
 *
 *   这是"误差修正"形式的写法，等价于：
 *   state = α × sample + (1-α) × state
 *
 *   优势：比直接加权平均少一次乘法，只有 1 次乘法和 2 次加减。
 *
 * =========================================================================
 * 初始化机制
 * =========================================================================
 *
 *   首次调用 efw_low_pass_run 时，若 filter->initialized == 0，
 *   自动调用 efw_low_pass_reset(filter, *sample)，
 *   将 state 设为第一个采样值并标记 initialized=1。
 *
 *   这样避免了从 state=0 起步的长时间阶跃响应。
 *   例如传感器实际读数 3.3V，首次调用 state 直接 = 3.3 而非从 0 慢慢上升。
 *
 * =========================================================================
 * α 参数调节指南
 * =========================================================================
 *
 *   α=0.01~0.05 → 强平滑，适合温度/湿度等缓变信号
 *   α=0.1~0.2  → 中度平滑，适合 ADC 采样、电池电压
 *   α=0.3~0.5  → 轻度平滑，适合 IMU 角速度等高频信号
 *   α=0.8~1.0  → 几乎无滤波，仅去除极端毛刺
 *
 *   调参技巧：
 *     先用 α=0.5 观察效果 → 噪声大就减小 α → 响应慢就增大 α
 *     α 的选择在"噪声抑制"和"响应延迟"之间权衡
 *
 *   等效截止频率：fc ≈ α / (2π × dt)
 *   例如 α=0.1, dt=0.01s → fc ≈ 1.6Hz (高于1.6Hz的信号被衰减)
 */

#include "efw/core/config.h"
#include "efw/algorithm/filter/low_pass.h"

#if EFW_ENABLE_ALGO_LOW_PASS  /**< 编译开关 */

/**
 * @brief 重置滤波器 —— 直接设置 state 并标记已初始化
 *
 * 用途：
 *   ① 传感器切换时直接同步到新传感器的当前读数
 *   ② 系统启动时避免从 0 开始缓慢上升
 *
 * @param filter 滤波器实例
 * @param value  初始状态值 (如传感器当前读数)
 */
void efw_low_pass_reset(efw_low_pass_t *filter, float value) {
    if (!filter) return;
    filter->state = value;          /* 直接设为目标值 */
    filter->initialized = 1;        /* 标记已初始化，下次 run 不再自动 reset */
}

/**
 * @brief 执行一次低通滤波 (可注册为 algo_ops.run)
 *
 * 首次调用时自动用第一个 sample 初始化 state。
 * 后续调用执行指数平均：state += α × (sample - state)
 *
 * @param ctx 指向 efw_low_pass_t
 * @param in  指向 float (新采样值)
 * @param out 指向 float (滤波输出)
 * @return EFW_OK / EFW_ERR_INVALID
 */
efw_status_t efw_low_pass_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    efw_low_pass_t *filter = (efw_low_pass_t *)ctx;
    const float *sample = (const float *)in;
    float *result = (float *)out;
    if (!filter || !sample || !result) return EFW_ERR_INVALID;
    if (in_size < sizeof(float) || out_size < sizeof(float)) return EFW_ERR_RANGE;
    if (filter->alpha < 0.0f || filter->alpha > 1.0f) return EFW_ERR_INVALID;

    /* 首次调用 → 自动初始化为第一个采样值 */
    if (!filter->initialized) efw_low_pass_reset(filter, *sample);

    /* 指数平均核心公式：state += α × (sample - state)
     * (sample - state) = 新值与旧值的误差 → α 控制修正速度 */
    filter->state += filter->alpha * (*sample - filter->state);

    *result = filter->state;        /* 输出当前滤波值 */
    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_LOW_PASS */
