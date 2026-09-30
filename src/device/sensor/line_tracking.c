/**
 * @file    line_tracking.c
 * @brief   循迹传感器 —— 加权误差 + 二值化偏差 + 巡线跟随器完整实现
 *
 * 本文件包含 6 个函数：
 *   ① efw_line_tracking_read           — 传感器读取 (委托)
 *   ② efw_line_tracking_error_weighted — ★ 加权误差 (模拟量)
 *   ③ efw_line_tracking_active_mask    — 激活通道位掩码 (数字量辅助)
 *   ④ efw_line_tracking_error_binary   — ★ 二值化偏差 (数字量)
 *   ⑤ efw_line_tracking_follow_diff    — 一步差速控制 (旧版)
 *   ⑥ efw_line_follower_bind           — 绑定巡线跟随器 (新版)
 *   ⑦ efw_line_follower_update         — 更新巡线跟随器 (新版)
 *
 * 由 EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_LINE_TRACKING 双开关控制。
 *
 * =========================================================================
 * 算法一：加权误差 (模拟量) — efw_line_tracking_error_weighted
 * =========================================================================
 *
 * 【原理】以传感器读数为权重的加权平均位置——"亮度分布的质心(一阶矩)"
 *   error = Σ(w[i] × v[i]) / Σ(v[i])
 *
 *   黑线吸收红外光 → 反射弱 → 该通道读数小 → 质心被"小值"拉向黑线位置
 *   实际上：大值(白)的通道把质心推向对面，小值(黑)的通道不贡献位置
 *   fact check：error>0 表示黑线偏右 (右侧 readings 低，大值集中在左侧)
 *
 * 【参数调节】
 *   权重范围         → 与 PID Kp 共同决定响应强度。推荐固定 weights 只调 Kp
 *   权重对称性       → 非对称可增强一侧敏感度 (如窄赛道可加重边缘权重)
 *   权重均匀性       → 非等距可增强边缘纠正力度 (防出轨)
 *
 *   通道数 vs 推荐权重：
 *     3ch: {-1, 0, 1}
 *     5ch: {-2, -1, 0, 1, 2}
 *     8ch: {-3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5}
 *     公式：weights[i] = i - (N-1)/2.0
 *
 * =========================================================================
 * 算法二：二值化偏差 (数字量) — efw_line_tracking_error_binary
 * =========================================================================
 *
 * 【原理】只对"检测到线"的通道取平均偏差
 *   遍历所有通道，若 value[i] == active_value (有信号)：
 *     sum += error_table[i], count++
 *   返回 sum / count
 *
 *   优点：不受环境光/反射强度影响 (只看 0/1)
 *   缺点：分辨率低 (尤其是单通道激活时，error 只能取离散的 error_table 值)
 *
 *   适合：使用 LM393 比较器 + 红外对管的低成本循迹模块
 *   不适合：需要精细偏差控制的高速循迹
 *
 *   error_table[] 的推荐值与模拟量 weights[] 相同：
 *     {-2, -1, 0, 1, 2} for 5ch
 *
 * 【辅助函数】efw_line_tracking_active_mask
 *   返回位掩码：第 i 位 = 1 表示通道 i 检测到线
 *   可用于：LED 指示、调试日志、模式判断 (如 "所有通道都无线 = 冲出赛道")
 */

#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/device/sensor/line_tracking.h"
#include "efw/algorithm/control/pid.h"
#include "efw/algorithm/registry.h"
#include "efw/device/actuator/motor.h"

#if EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_LINE_TRACKING

/* ==================================================================
 *  ① 传感器读取 (委托给通用 sensor_read)
 * ================================================================== */

efw_status_t efw_line_tracking_read(const char *name, efw_line_tracking_data_t *out) {
    if (!out) return EFW_ERR_INVALID;
    return efw_sensor_read(name, out, (uint16_t)sizeof(*out));
}

/* ==================================================================
 *  ② 加权误差 (模拟量) —— 亮度质心算法
 * ================================================================== */

float efw_line_tracking_error_weighted(const efw_line_tracking_data_t *data, const float *weights) {
    float weighted_sum = 0.0f;  /* 分子：Σ(w[i] × v[i]) */
    float total = 0.0f;         /* 分母：Σ(v[i]) */

    if (!data || !weights || data->count == 0) return 0.0f;

    for (uint8_t i = 0; i < data->count && i < EFW_LINE_TRACKING_MAX_CHANNELS; ++i) {
        float value = (float)data->value[i];    /* uint16_t → float */
        weighted_sum += weights[i] * value;     /* 加权位置累加 */
        total += value;                          /* 总亮度累加 */
    }

    if (total <= 0.0f) return 0.0f;             /* 除零保护 */
    return weighted_sum / total;                /* 归一化 → 加权平均位置 */
}

/* ==================================================================
 *  ③ 激活通道位掩码 (数字量辅助函数)
 * ================================================================== */

/**
 * @brief 返回一个 uint16_t 位掩码，第 i 位=1 表示通道 i 检测到线
 *
 * 用于数字量循迹——只判断"有/无黑线"，不考虑信号强度。
 * 最多 16 通道 (uint16_t 限制)。
 *
 * @param active_value "有线"的电平 (如 1=高有效, 0=低有效，取决于比较器极性)
 */
uint16_t efw_line_tracking_active_mask(const efw_line_tracking_data_t *data, uint16_t active_value) {
    uint16_t mask = 0;

    if (!data) return 0;

    for (uint8_t i = 0; i < data->count && i < EFW_LINE_TRACKING_MAX_CHANNELS && i < 16; ++i) {
        if (data->value[i] == active_value) mask |= (uint16_t)(1u << i);  /* 通道 i 激活 → 置位 */
    }

    return mask;
}

/* ==================================================================
 *  ④ 二值化偏差 (数字量) —— 激活通道的平均偏差
 * ================================================================== */

/**
 * @brief 所有"检测到线"的通道的平均偏差
 *
 * 与加权误差不同——这里每个激活通道等权 (1/count)，不按信号强度加权。
 * 适合数字量循迹传感器 (0/1 输出)。
 *
 * error_table[] = 各通道的空间偏差值 (如 {-2,-1,0,1,2})
 * active_value  = "检测到线"的电平
 */
float efw_line_tracking_error_binary(const efw_line_tracking_data_t *data,
                                     const float *error_table, uint16_t active_value) {
    float sum = 0.0f;   /* 所有激活通道的偏差总和 */
    float count = 0.0f; /* 激活通道计数 */

    if (!data || !error_table || data->count == 0) return 0.0f;

    for (uint8_t i = 0; i < data->count && i < EFW_LINE_TRACKING_MAX_CHANNELS; ++i) {
        if (data->value[i] == active_value) {  /* 仅处理检测到线的通道 */
            sum += error_table[i];              /* 累加偏差 */
            count += 1.0f;                      /* 计数 */
        }
    }

    if (count <= 0.0f) return 0.0f;            /* 所有通道都未检测到线 → 返回 0 */
    return sum / count;                         /* 平均偏差 */
}

/* ==================================================================
 *  ⑤ 一步差速控制 (旧版 API)
 *
 *  内部：read → weighted_error → PID → motor_set_diff
 *  使用 efw_motor_set_diff (无速度限制)
 * ================================================================== */

efw_status_t efw_line_tracking_follow_diff(const char *sensor_name, const char *pid_name,
                                           const char *left_motor, const char *right_motor,
                                           const float *weights, float base_speed, float dt,
                                           float *out_error, float *out_turn) {
#if EFW_ENABLE_ALGORITHM && EFW_ENABLE_ALGO_PID && EFW_ENABLE_ACTUATOR && EFW_ENABLE_ACTUATOR_MOTOR
    efw_line_tracking_data_t data;
    efw_pid_input_t pid_in;
    efw_pid_output_t pid_out;
    float error;
    efw_status_t s;

    if (!weights || dt <= 0.0f) return EFW_ERR_INVALID;

    /* ① 读取传感器 */
    s = efw_line_tracking_read(sensor_name, &data);
    if (s != EFW_OK) return s;

    /* ② 加权误差 ← 目标 setpoint=0 (黑线居中) */
    error = efw_line_tracking_error_weighted(&data, weights);
    pid_in.setpoint = 0.0f;
    pid_in.feedback = error;
    pid_in.dt = dt;

    /* ③ PID 计算 */
    s = efw_algo_run(pid_name, &pid_in, sizeof(pid_in), &pid_out, sizeof(pid_out));
    if (s != EFW_OK) return s;

    /* ④ 差速驱动 (无速度限制) */
    s = efw_motor_set_diff(left_motor, right_motor, base_speed, pid_out.output);
    if (s != EFW_OK) return s;

    /* ⑤ 可选输出 */
    if (out_error) *out_error = error;
    if (out_turn) *out_turn = pid_out.output;
    return EFW_OK;
#else
    EFW_UNUSED(sensor_name); EFW_UNUSED(pid_name); EFW_UNUSED(left_motor);
    EFW_UNUSED(right_motor); EFW_UNUSED(weights); EFW_UNUSED(base_speed);
    EFW_UNUSED(dt); EFW_UNUSED(out_error); EFW_UNUSED(out_turn);
    return EFW_ERR_INVALID;
#endif
}

/* ==================================================================
 *  ⑥ 巡线跟随器绑定 (新版 API) —— 一次性预取所有 ops 指针
 *
 *  通过名称查找 sensor/pid/left_motor/right_motor 并缓存指针。
 *  后续 update 时直接使用缓存指针，无需每次字符串查找。
 * ================================================================== */

efw_status_t efw_line_follower_bind(efw_line_follower_t *follower,
                                    const char *sensor_name, const char *pid_name,
                                    const char *left_motor, const char *right_motor,
                                    const float *weights, float base_speed,
                                    float min_speed, float max_speed, float dt) {
    efw_line_follower_config_t config;

    config.sensor_name = sensor_name;
    config.pid_name = pid_name;
    config.left_motor = left_motor;
    config.right_motor = right_motor;
    config.weights = weights;
    config.base_speed = base_speed;
    config.min_speed = min_speed;
    config.max_speed = max_speed;
    config.dt = dt;
    config.active_value = 1u;
    config.binary_mode = 0u;

    return efw_line_follower_bind_config(follower, &config);
}

efw_status_t efw_line_follower_bind_config(efw_line_follower_t *follower,
                                           const efw_line_follower_config_t *config) {
#if EFW_ENABLE_ALGORITHM && EFW_ENABLE_ALGO_PID && EFW_ENABLE_ACTUATOR && EFW_ENABLE_ACTUATOR_MOTOR
    efw_status_t s;

    if (!follower || !config || !config->weights || config->dt <= 0.0f) return EFW_ERR_INVALID;

    /* 逐个查找并缓存 ops 指针 (注册时校验过的名称此时应全部存在) */
    s = efw_sensor_get(config->sensor_name, &follower->sensor);
    if (s != EFW_OK) return s;
    s = efw_algo_get(config->pid_name, &follower->pid);
    if (s != EFW_OK) return s;
    s = efw_actuator_get(config->left_motor, &follower->left_motor);
    if (s != EFW_OK) return s;
    s = efw_actuator_get(config->right_motor, &follower->right_motor);
    if (s != EFW_OK) return s;

    /* 缓存运行参数 */
    follower->weights = config->weights;
    follower->active_value = config->active_value;
    follower->binary_mode = config->binary_mode;
    follower->base_speed = config->base_speed;
    follower->min_speed = config->min_speed;
    follower->max_speed = config->max_speed;
    follower->dt = config->dt;
    return EFW_OK;
#else
    EFW_UNUSED(follower); EFW_UNUSED(config);
    return EFW_ERR_INVALID;
#endif
}

/* ==================================================================
 *  ⑦ 巡线跟随器更新 (新版 API) —— 使用缓存指针的完整控制链路
 *
 *  内部：read → weighted_error → PID → motor_set_diff_limited (限速!)
 *
 *  比 follow_diff 的优势：
 *    ① 使用缓存 ops 指针 — 无字符串查找开销
 *    ② 使用 set_diff_limited — 自带速度限幅
 *    ③ 代码更简洁 — 一行调用完成全部操作
 * ================================================================== */

efw_status_t efw_line_follower_update(efw_line_follower_t *follower, float *out_error, float *out_turn) {
#if EFW_ENABLE_ALGORITHM && EFW_ENABLE_ALGO_PID && EFW_ENABLE_ACTUATOR && EFW_ENABLE_ACTUATOR_MOTOR
    efw_line_tracking_data_t data;
    efw_pid_input_t pid_in;
    efw_pid_output_t pid_out;
    efw_motor_cmd_t left_cmd;
    efw_motor_cmd_t right_cmd;
    float error;
    float left_speed;
    float right_speed;
    efw_status_t s;

    if (!follower) return EFW_ERR_INVALID;

    /* ① 读取传感器 (使用缓存指针直接调用，O(1)) */
    s = follower->sensor->read(follower->sensor->ctx, &data, (uint16_t)sizeof(data));
    if (s != EFW_OK) return s;

    /* ② 误差计算：数字模块用二值误差，模拟模块用加权误差 */
    if (follower->binary_mode) {
        error = efw_line_tracking_error_binary(&data, follower->weights, follower->active_value);
    } else {
        error = efw_line_tracking_error_weighted(&data, follower->weights);
    }

    /* ③ PID 计算 */
    pid_in.setpoint = 0.0f;
    pid_in.feedback = error;
    pid_in.feedforward = 0.0f;
    pid_in.dt = follower->dt;
    s = follower->pid->run(follower->pid->ctx, &pid_in, sizeof(pid_in), &pid_out, sizeof(pid_out));
    if (s != EFW_OK) return s;

    /* ④ 差速公式 + 限速 */
    left_speed = follower->base_speed - pid_out.output;
    right_speed = follower->base_speed + pid_out.output;

    /* 限速钳位 (保证不反转、不超速) */
    if (left_speed < follower->min_speed) left_speed = follower->min_speed;
    if (left_speed > follower->max_speed) left_speed = follower->max_speed;
    if (right_speed < follower->min_speed) right_speed = follower->min_speed;
    if (right_speed > follower->max_speed) right_speed = follower->max_speed;

    /* ⑤ 写入左电机 */
    left_cmd.speed = (left_speed >= 0.0f) ? left_speed : -left_speed;
    left_cmd.direction = (left_speed > 0.0f) ? 1.0f : ((left_speed < 0.0f) ? -1.0f : 0.0f);
    s = follower->left_motor->write(follower->left_motor->ctx, &left_cmd, (uint16_t)sizeof(left_cmd));
    if (s != EFW_OK) return s;

    /* ⑥ 写入右电机 */
    right_cmd.speed = (right_speed >= 0.0f) ? right_speed : -right_speed;
    right_cmd.direction = (right_speed > 0.0f) ? 1.0f : ((right_speed < 0.0f) ? -1.0f : 0.0f);
    s = follower->right_motor->write(follower->right_motor->ctx, &right_cmd, (uint16_t)sizeof(right_cmd));
    if (s != EFW_OK) return s;

    /* ⑦ 可选输出 */
    if (out_error) *out_error = error;
    if (out_turn) *out_turn = pid_out.output;
    return EFW_OK;
#else
    EFW_UNUSED(follower); EFW_UNUSED(out_error); EFW_UNUSED(out_turn);
    return EFW_ERR_INVALID;
#endif
}

#endif /* EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_LINE_TRACKING */
