/**
 * @file    motor.c
 * @brief   电机执行器高级 API 实现：符号分离 + 差速驱动 + 限速差速
 *
 * 本文件由 EFW_ENABLE_ACTUATOR && EFW_ENABLE_ACTUATOR_MOTOR 双开关控制。
 *
 * =========================================================================
 * 核心算法
 * =========================================================================
 *
 *   efw_motor_set_diff(left, right, base_speed, turn):
 *     左轮 = base_speed - turn
 *     右轮 = base_speed + turn
 *
 *   efw_motor_set_diff_limited(left, right, base, turn, min, max):
 *     左轮 = clamp(base_speed - turn, min, max)
 *     右轮 = clamp(base_speed + turn, min, max)
 *
 *   差速原理：turn>0 → 左减速右加速 → 右转；turn<0 → 反向。
 *
 *   set_diff_limited 的优势：
 *     设 min_speed=0 → 保证速度不会为负 (不会意外反转)
 *     设 max_speed=100 → 保证不超过 PWM 上限
 *     对于循迹小车，强烈推荐使用 set_diff_limited。
 */

#include "efw/core/config.h"
#include "efw/device/actuator/motor.h"

#if EFW_ENABLE_ACTUATOR && EFW_ENABLE_ACTUATOR_MOTOR

/** @brief 浮点数绝对值 */
static float abs_float(float value) {
    return value < 0.0f ? -value : value;
}

/**
 * @brief 浮点数钳位 —— 将 value 限制在 [min_value, max_value]
 * 当 min≥max 时返回原值 (异常配置保护)
 */
static float clamp_float(float value, float min_value, float max_value) {
    if (min_value < max_value) {
        if (value < min_value) return min_value;
        if (value > max_value) return max_value;
    }
    return value;
}

/**
 * @brief 从带符号速度中提取方向
 * speed > 0 → 1.0 (正转), speed < 0 → -1.0 (反转), speed = 0 → 0.0 (停止)
 */
static float direction_from_speed(float speed) {
    if (speed > 0.0f) return 1.0f;
    if (speed < 0.0f) return -1.0f;
    return 0.0f;
}

efw_status_t efw_motor_write(const char *name, float speed, float direction) {
    efw_motor_cmd_t cmd;
    cmd.speed = speed;
    cmd.direction = direction;
    return efw_actuator_write(name, &cmd, (uint16_t)sizeof(cmd));
}

efw_status_t efw_motor_set_speed(const char *name, float speed) {
    return efw_motor_write(name, abs_float(speed), direction_from_speed(speed));
}

efw_status_t efw_motor_stop(const char *name) {
    return efw_motor_write(name, 0.0f, 0.0f);
}

/**
 * @brief 差速驱动 (无速度限制)
 *
 * 左轮 = base - turn, 右轮 = base + turn
 * 注意：无速度限制，turn 过大可能导致某轮反转。
 */
efw_status_t efw_motor_set_diff(const char *left_motor, const char *right_motor,
                                float base_speed, float turn) {
    efw_status_t s;
    s = efw_motor_set_speed(left_motor, base_speed - turn);
    if (s != EFW_OK) return s;
    return efw_motor_set_speed(right_motor, base_speed + turn);
}

/**
 * @brief 限速差速驱动 ★ 推荐使用
 *
 * 对差速后的每轮速度单独做 clamp：
 *   left  = clamp(base_speed - turn, min_speed, max_speed)
 *   right = clamp(base_speed + turn, min_speed, max_speed)
 *
 * 即使 PID 输出异常大的 turn 值，速度也不会超出 [min, max] 范围。
 *
 * min_speed=0 → 不会反转；max_speed=100 → 不会超过 PWM 上限。
 */
efw_status_t efw_motor_set_diff_limited(const char *left_motor, const char *right_motor,
                                        float base_speed, float turn,
                                        float min_speed, float max_speed) {
    efw_status_t s;
    float left_speed = clamp_float(base_speed - turn, min_speed, max_speed);
    float right_speed = clamp_float(base_speed + turn, min_speed, max_speed);

    s = efw_motor_set_speed(left_motor, left_speed);
    if (s != EFW_OK) return s;
    return efw_motor_set_speed(right_motor, right_speed);
}

#endif
