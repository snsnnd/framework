/**
 * @file    attitude_complementary.h
 * @brief   互补滤波器 —— 加速度计 + 陀螺仪融合姿态角估算
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 *   互补滤波器是无人机/机器人姿态估计中最简单实用的算法。
 *   它融合两个传感器的优势，互相弥补对方的缺陷。
 *
 * 【两个传感器的特性】
 *
 *   加速度计 → 可以算出绝对角度 (roll/pitch)，不受时间影响
 *     ✓ 静态精度高、无漂移
 *     ✗ 动态时受运动加速度干扰，噪声大
 *
 *   陀螺仪 → 对角速度积分得到角度变化量
 *     ✓ 动态响应快、不受加速度干扰
 *     ✗ 积分会累积误差，产生长期漂移 (几秒就偏几度)
 *
 * 【互补滤波公式】
 *
 *   ① 从加速度计计算角度 (atan2 反三角函数)：
 *     accel_roll  = atan2(ay, az) × 180/π
 *     accel_pitch = atan2(-ax, √(ay²+az²)) × 180/π
 *
 *   ② 互补融合 (α 控制"信任权重")：
 *     roll  = α × (roll  + gx × dt)   + (1-α) × accel_roll
 *     pitch = α × (pitch + gy × dt)   + (1-α) × accel_pitch
 *
 *   解读：
 *     α = 信任陀螺仪的比例 (短期信任)
 *     1-α = 信任加速度计的比例 (长期修正)
 *
 *     α 接近 1.0 (如 0.98) → 非常信任陀螺仪，动态响应快，漂移修正慢
 *     α 接近 0   (如 0.90) → 非常信任加速度计，角度稳但噪声大
 *
 * 【参数调节】
 *   α = 0.98  — 最常用的值，适合大多数场景
 *               gyro 贡献 98%，accel 用 2% 缓慢修正漂移
 *   α = 0.95  — 加速度计噪声较大时 (如振动环境)，降低 α 减小噪声
 *   α = 0.99  — 运动非常剧烈时 (如特技飞行)，提高 α 减少运动加速度干扰
 *   调节原则：振动大 → 增大 α；需要快速纠正漂移 → 减小 α
 *
 * 【关于 dt】
 *   dt 是陀螺仪积分的时间步长。gx 的单位是 °/s，乘以 dt(秒) 得到角度增量。
 *   例如：gx=100°/s, dt=0.01s → 角度增量 = 1°
 *
 * 【局限】
 *   ① 只计算 roll 和 pitch，不支持 yaw (偏航需要磁力计)
 *   ② 依赖 atan2 和 sqrt (调用标准库 math 函数)
 *   ③ 不适合长时间倒置/垂直状态 (atan2 在 az≈0 时不稳定)
 */

#ifndef EFW_ALGORITHM_ATTITUDE_COMPLEMENTARY_H
#define EFW_ALGORITHM_ATTITUDE_COMPLEMENTARY_H

#include "efw/core/common.h"

/**
 * @brief 互补滤波器状态
 *
 * @field roll        当前 roll 角估计值 (度) [内部状态]
 * @field pitch       当前 pitch 角估计值 (度) [内部状态]
 * @field alpha       陀螺仪信任权重 (0~1)。0.98 为常用值。
 *                    越接近 1 = 越信陀螺仪 = 动态响应快/漂移修正慢
 * @field initialized 是否已初始化 [内部状态]。首次调用时用加速度计角度初始化
 */
typedef struct {
    float roll;             /**< [内部] roll 角 (度) */
    float pitch;            /**< [内部] pitch 角 (度) */
    float alpha;            /**< 陀螺仪权重 (0~1, 推荐 0.98) */
    uint8_t initialized;    /**< [内部] 首次调用标记 */
} efw_attitude_complementary_t;

/**
 * @brief 互补滤波器输入
 *
 * @field ax/ay/az 加速度计读数 (m/s² 或 g，单位不影响 atan2 比值)
 *                  静止水平时：ax≈0, ay≈0, az≈+1g
 * @field gx/gy    陀螺仪角速度读数 (°/s)。gz 未使用(互补滤波不计算 yaw)
 * @field dt       距上次调用的时间间隔 (秒)，必须 > 0
 */
typedef struct {
    float ax, ay, az;   /**< 加速度计 (任意单位，比值运算) */
    float gx, gy;       /**< 陀螺仪角速度 (°/s) */
    float dt;           /**< 时间间隔 (秒) */
} efw_attitude_input_t;

/**
 * @brief 互补滤波器输出
 * @field roll  roll 角 (度, -180 ~ +180)
 * @field pitch pitch 角 (度, -90 ~ +90)
 */
typedef struct {
    float roll;     /**< 横滚角 (度) */
    float pitch;    /**< 俯仰角 (度) */
} efw_attitude_output_t;

/**
 * @brief 执行一次互补滤波姿态估计 (可注册为 algo_ops.run)
 *
 * @param ctx 指向 efw_attitude_complementary_t
 * @param in  指向 efw_attitude_input_t
 * @param out 指向 efw_attitude_output_t
 * @return EFW_OK / EFW_ERR_INVALID (参数非法, dt≤0, alpha 超出 [0,1])
 */
efw_status_t efw_attitude_complementary_run(void *ctx, const void *in, void *out);

#endif
