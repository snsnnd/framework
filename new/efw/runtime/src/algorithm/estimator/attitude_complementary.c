/**
 * @file    attitude_complementary.c
 * @brief   互补滤波器实现 —— 加速度计 + 陀螺仪融合 roll/pitch 姿态估计
 *
 * 由 EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY 宏控制编译。
 *
 * =========================================================================
 * 完整算法步骤
 * =========================================================================
 *
 *   ① 从加速度计计算绝对角度 (atan2 反三角)：
 *     accel_roll  = atan2(ay, az) × 180/π
 *     accel_pitch = atan2(-ax, √(ay²+az²)) × 180/π
 *
 *     为什么 atan2(ay, az) 能算 roll？
 *       静止水平时：ay≈0, az≈+g → atan2(0, g)=0° ✓
 *       右侧下沉时：ay>0, az 减小 → atan2(正, 正)=正角 ✓
 *
 *     为什么 pitch 公式中有负号和 sqrt？
 *       atan2(-ax, √(ay²+az²))
 *       静止水平时：ax≈0 → atan2(0, g)=0° ✓
 *       抬头时：ax<0 → atan2(正, g)=正角 ✓
 *       分母用 √(ay²+az²) 而不是 az——当 roll≠0 时 az 已经偏离重力方向，
 *       √(ay²+az²) 更准确地代表"垂直于 X 轴的分量"
 *
 *   ② 陀螺仪积分 (预测)：
 *     预测 roll  = 上次 roll  + gx × dt
 *     预测 pitch = 上次 pitch + gy × dt
 *
 *   ③ 互补融合 (修正)：
 *     roll  = α × 预测 roll  + (1-α) × accel_roll
 *     pitch = α × 预测 pitch + (1-α) × accel_pitch
 *
 *     α 控制信任权重：
 *       α=0.98 → 98% 信任陀螺仪 (动态跟得上)，2% 信任加速度计 (缓慢修正漂移)
 *
 * 【初始化】
 *   首次调用时直接用加速度计角度初始化 roll/pitch，
 *   避免从 0 开始的长收敛过程。
 *
 * =========================================================================
 * 依赖说明
 * =========================================================================
 *
 *   需要标准库的 atan2() 和 sqrt() 函数。
 *   用 extern 声明而非 #include <math.h> —— 由用户确保链接时这些符号可用。
 *   这样做的好处：不强制引入 math.h (某些嵌入式工具链的 math.h 可能不可用)。
 *
 *   常数 EFW_RAD_TO_DEG = 180/π ≈ 57.29578
 *   用于将 atan2 返回的弧度值转换为角度值。
 *
 * =========================================================================
 * 参数调节
 * =========================================================================
 *
 *   α 是最重要的参数：
 *     α=0.98  —— 推荐默认值。适合大多数场景
 *     α=0.95  —— 振动环境，需要更多加速度计修正
 *     α=0.99  —— 剧烈运动，陀螺仪主导
 *
 *   调节原则：
 *     角度漂移 (长期不准) → 减小 α (增强加速度计修正)
 *     角度抖动 (短期噪声) → 增大 α (增强陀螺仪滤波)
 *
 *   dt (控制周期)：
 *     必须是实际两次调用之间的时间间隔。
 *     如果中断频率不稳定，每次用定时器实测 dt 传入。
 *     典型嵌入式 IMU 读取周期：1ms~10ms。
 */

#include "efw/core/config.h"
#include "efw/algorithm/estimator/attitude_complementary.h"

#if EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY  /**< 编译开关 */

/* 外部声明：依赖标准库的 atan2 和 sqrt，由链接时提供 */
extern double atan2(double, double);    /**< 标准库反三角函数 */
extern double sqrt(double);             /**< 标准库平方根 */

/** @brief 弧度转角度常数：180/π */
#define EFW_RAD_TO_DEG 57.29577951308232f

/**
 * @brief 执行一次互补滤波姿态估计 (可注册为 algo_ops.run)
 *
 * 完整 4 步算法见文件头注释。
 *
 * @param ctx 指向 efw_attitude_complementary_t
 * @param in  指向 efw_attitude_input_t (ax/ay/az/gx/gy/dt)
 * @param out 指向 efw_attitude_output_t (roll/pitch)
 * @return EFW_OK / EFW_ERR_INVALID
 */
efw_status_t efw_attitude_complementary_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    efw_attitude_complementary_t *est = (efw_attitude_complementary_t *)ctx;
    const efw_attitude_input_t *input = (const efw_attitude_input_t *)in;
    efw_attitude_output_t *result = (efw_attitude_output_t *)out;
    float accel_roll;
    float accel_pitch;
    if (!est || !input || !result) return EFW_ERR_INVALID;
    if (in_size < sizeof(efw_attitude_input_t) || out_size < sizeof(efw_attitude_output_t)) return EFW_ERR_RANGE;

    /* 参数校验：指针非空 + dt>0 + α 在 [0,1] 范围 */
    if (!est || !input || !result || input->dt <= 0.0f ||
        est->alpha < 0.0f || est->alpha > 1.0f)
        return EFW_ERR_INVALID;

    /* ① 加速度计 → 绝对角度 (atan2 反三角，弧度转度) */
    accel_roll = (float)(atan2((double)input->ay, (double)input->az) * EFW_RAD_TO_DEG);
    accel_pitch = (float)(atan2((double)-input->ax,
                       sqrt((double)(input->ay * input->ay + input->az * input->az)))
                       * EFW_RAD_TO_DEG);

    /* 首次调用 → 用加速度计角度直接初始化 (跳过收敛过程) */
    if (!est->initialized) {
        est->roll = accel_roll;             /* 初始 roll = 加速度计 roll */
        est->pitch = accel_pitch;           /* 初始 pitch = 加速度计 pitch */
        est->initialized = 1;               /* 标记已初始化 */
    }

    /* ②+③ 互补融合：
     *   (est->roll + gx×dt)  = 陀螺仪积分预测
     *   α × 预测 + (1-α) × accel = 互补加权平均 */
    est->roll = est->alpha * (est->roll + input->gx * input->dt)
              + (1.0f - est->alpha) * accel_roll;

    est->pitch = est->alpha * (est->pitch + input->gy * input->dt)
               + (1.0f - est->alpha) * accel_pitch;

    /* ④ 输出结果 */
    result->roll = est->roll;
    result->pitch = est->pitch;
    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY */
