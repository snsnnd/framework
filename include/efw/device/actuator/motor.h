/**
 * @file    motor.h
 * @brief   电机执行器 —— 差速驱动、单电机控制、紧急停止、限速差速
 *
 * 本文件在 efw_actuator_write() 基础上提供了电机专用的便捷接口。
 *
 * =========================================================================
 * 核心功能
 * =========================================================================
 *
 *   ① efw_motor_write(name, speed, direction) — 最底层的电机指令
 *   ② efw_motor_set_speed(name, speed) — 符号自动分离 (★ 最常用)
 *   ③ efw_motor_stop(name) — 紧急停止
 *   ④ efw_motor_set_diff(left, right, base_speed, turn) — ★ 差速驱动
 *   ⑤ efw_motor_set_diff_limited(left, right, base, turn, min, max) — 限速差速
 *
 * =========================================================================
 * 差速转向原理
 * =========================================================================
 *
 *   双轮差速小车通过左右轮转速差异实现转向：
 *     turn = 0   → left = right = base_speed → 直行
 *     turn > 0   → left 减速, right 加速 → 右转
 *     turn < 0   → left 加速, right 减速 → 左转
 *
 *   set_diff         — 不限制速度范围，可能因 turn 过大导致反转
 *   set_diff_limited — 用 clamp 将每轮速度限制在 [min_speed, max_speed]
 *                       避免反转 (min_speed≥0) 或超速 (max_speed≤100)
 *
 *   参数调节建议：
 *     base_speed — 基础巡航速度，应 > |turn_max|
 *     min_speed  — 设为 0 可防止反转 (最安全)
 *     max_speed  — 设为 100 对应 PWM 100% 占空比
 */

#ifndef EFW_ACTUATOR_MOTOR_H
#define EFW_ACTUATOR_MOTOR_H

#include "efw/core/common.h"
#include "efw/device/actuator.h"

/** @brief 差速驱动指令结构体 */
typedef struct {
    const char *left_motor;     /**< 左电机注册名称 */
    const char *right_motor;    /**< 右电机注册名称 */
    float base_speed;           /**< 基础巡航速度 (>0) */
    float turn;                 /**< 转向修正量 (正=右转, 负=左转) */
} efw_motor_diff_cmd_t;

efw_status_t efw_motor_write(const char *name, float speed, float direction);
efw_status_t efw_motor_set_speed(const char *name, float speed);
efw_status_t efw_motor_stop(const char *name);

/**
 * @brief 差速驱动 (无速度限制)
 *
 * left = base_speed - turn, right = base_speed + turn
 * 不限制速度范围——turn 过大可能导致反转。
 */
efw_status_t efw_motor_set_diff(const char *left_motor, const char *right_motor,
                                float base_speed, float turn);

/**
 * @brief 限速差速驱动 ★ 推荐使用的安全版本
 *
 * 在差速公式后对每轮速度单独做 clamp 限制：
 *   left  = clamp(base_speed - turn, min_speed, max_speed)
 *   right = clamp(base_speed + turn, min_speed, max_speed)
 *
 * 这比 set_diff 更安全——即使 turn 非常大，速度也不会超出 [min, max]。
 *
 * @param left_motor  左电机名称
 * @param right_motor 右电机名称
 * @param base_speed  基础巡航速度
 * @param turn        转向修正量 (来自 PID 输出)
 * @param min_speed   最小速度限制 (设 0 可防止反转)
 * @param max_speed   最大速度限制 (如 100 = PWM 100%)
 */
efw_status_t efw_motor_set_diff_limited(const char *left_motor, const char *right_motor,
                                        float base_speed, float turn,
                                        float min_speed, float max_speed);

#endif
