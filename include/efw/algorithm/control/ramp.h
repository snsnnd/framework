/**
 * @file    ramp.h
 * @brief   斜坡控制器 —— 对目标值的升降速率进行限制
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 *   斜坡控制器 (Ramp / Slew Rate Limiter) 限制输出值的变化速率。
 *   当目标值发生阶跃变化时，输出不会立即跳到目标值，而是以固定速率
 *   斜坡逼近——避免执行器的突然冲击。
 *
 * 【公式】
 *   delta  = target - value                  — 当前值与目标的差距
 *   limit  = rate × dt                       — 本周期允许的最大变化量
 *   if (delta >  limit) delta =  limit       — 不超过上升限速
 *   if (delta < -limit) delta = -limit       — 不超过下降限速
 *   value += delta                            — 更新当前值
 *   output = value                            — 斜坡后的输出
 *
 * 【上升/下降速率分离】
 *   rise_rate — 目标值增大时的最大速率 (正值, 单位/秒)
 *   fall_rate — 目标值减小时的的最大速率 (正值, 单位/秒)
 *   分离的好处：加速可以很快，但减速要平滑（如电机急停保护）
 *
 *   例如 rise_rate=100, fall_rate=50：
 *     加速时每秒最多增加 100
 *     减速时每秒最多减少 50 (更平滑的减速)
 *
 * 【典型用途】
 *   ① 电机速度斜坡：避免速度指令突变导致电流冲击
 *   ② 舵机角度平滑：避免角度阶跃导致机械抖动
 *   ③ LED 渐变：亮度变化更自然
 *   ④ PID setpoint 平滑：设定值突然改变时，让 PID 跟踪一个渐变的目标
 *
 * 【参数调节】
 *   rise_rate — 上升速率。值越大响应越快，但失去斜坡保护效果
 *               电机场景：100~500 单位/秒 (取决于速度量纲)
 *   fall_rate — 下降速率。通常 ≤ rise_rate (减速比加速更平滑)
 *               设为 0 或负数 → run 返回 EFW_ERR_INVALID
 *   通过 efw_ramp_reset() 可直接跳到目标值 (跳过斜坡，用于初始化)
 */

#ifndef EFW_ALGORITHM_RAMP_H
#define EFW_ALGORITHM_RAMP_H

#include "efw/core/common.h"

/**
 * @brief 斜坡控制器状态
 *
 * @field value     当前输出值 [内部状态，由 run 更新]
 * @field rise_rate 上升速率 (正值, 单位/秒)。值越大加速越快
 * @field fall_rate 下降速率 (正值, 单位/秒)。值越大减速越快
 */
typedef struct {
    float value;        /**< [内部] 当前斜坡输出值 */
    float rise_rate;    /**< 上升速率限制 (>0, 单位/秒) */
    float fall_rate;    /**< 下降速率限制 (>0, 单位/秒) */
} efw_ramp_t;

/**
 * @brief 斜坡控制器单次输入
 * @field target 目标值 (最终要达到的值)
 * @field dt     距上次调用的时间间隔 (秒)，必须 > 0
 */
typedef struct {
    float target;       /**< 目标值 */
    float dt;           /**< 时间间隔 (秒) */
} efw_ramp_input_t;

/**
 * @brief 重置斜坡值 —— 直接跳到指定值，不经过斜坡
 * 用于初始化时设置起始值，避免从 0 开始的不必要斜坡过程。
 * @param ramp  控制器实例
 * @param value 初始值
 */
void efw_ramp_reset(efw_ramp_t *ramp, float value);

/**
 * @brief 执行一次斜坡计算 (可注册为 algo_ops.run)
 *
 * @param ctx 指向 efw_ramp_t
 * @param in  指向 efw_ramp_input_t (target + dt)
 * @param out 指向 float (斜坡后的当前值写入此处)
 * @return EFW_OK / EFW_ERR_INVALID (参数非法, dt≤0, rate<0)
 */
efw_status_t efw_ramp_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size);

#endif
