/**
 * @file    line_tracking.h
 * @brief   循迹传感器 —— 灰度/红外反射阵列 + 数字二值化循迹 + 巡线跟随器
 *
 * =========================================================================
 * 传感器类型：模拟 vs 数字
 * =========================================================================
 *
 *   循迹传感器有两种常见输出模式：
 *
 *   【模拟量输出】— 输出连续电压 (0~VCC)，反映反射光强度
 *     白/浅色 → 高电压 (~3V), 黑/深色 → 低电压 (~0V)
 *     需要接 ADC 读取。适合精细控制场景。
 *     配套算法：efw_line_tracking_error_weighted() — 加权平均位置
 *
 *   【数字量输出】— 输出 0/1 开关量，通过比较器 (LM393) 阈值化
 *     低于阈值 (黑线) → 0 (或 1，取决于极性), 高于阈值 → 1 (或 0)
 *     直接接 GPIO 即可，不需要 ADC。适合简单巡线。
 *     配套算法：efw_line_tracking_error_binary() — 等权平均偏差
 *     辅助函数：efw_line_tracking_active_mask() — 产生激活通道位掩码
 *
 * =========================================================================
 * 加权误差算法 (模拟量) — efw_line_tracking_error_weighted
 * =========================================================================
 *
 *   error = Σ(weights[i] × value[i]) / Σ(value[i])
 *
 *   以传感器读数为权重的加权平均位置——"亮度质心"。
 *   error=0 黑线居中, error>0 偏右, error<0 偏左。
 *   这个 error 可直接作为 PID 的 feedback 输入。
 *
 *   参数调节：见 line_tracking.c 文件头注释。
 *
 * =========================================================================
 * 二值化误差算法 (数字量) — efw_line_tracking_error_binary
 * =========================================================================
 *
 *   与加权误差不同，二值化算法只关心"哪些通道检测到了线"——忽略信号强度。
 *   每个通道只区分 0 (无线) 和 1 (有线)。
 *
 *   算法：
 *     遍历所有通道 i，若 value[i] == active_value (检测到线)：
 *       sum += error_table[i]  (累加该通道的偏差值)
 *       count += 1
 *     返回 sum / count (所有检测到线的通道的平均偏差)
 *
 *   error_table[] 为每个通道预定义的偏差值 (如 {-2,-1,0,1,2})。
 *   返回的是平均偏差——这意味着如果多条线同时检测到，取它们的中心。
 *
 *   示例：error_table={-2,-1,0,1,2}, active_value=1
 *     数据={0, 0, 1, 0, 0} → 仅通道2检测到线 → error=0 (线在中心)
 *     数据={1, 0, 0, 0, 0} → 仅通道0检测到线 → error=-2 (线最左边)
 *     数据={1, 1, 0, 0, 0} → 通道0,1有信号 → error=(-2-1)/2=-1.5 (线偏左)
 *
 * =========================================================================
 * 巡线跟随器 (efw_line_follower_t) —— 高层抽象
 * =========================================================================
 *
 *   efw_line_follower_t 将循迹控制的所有组件封装为一个对象：
 *     传感器 + PID + 左电机 + 右电机 + 权重 + 速度参数
 *
 *   使用流程：
 *     ① efw_line_follower_bind(&follower, ...) — 绑定所有组件 (一次性)
 *     ② efw_line_follower_update(&follower, ...) — 每周期执行 (在循环中调用)
 *
 *   这比每次都手动调用 sensor_read → error_weighted → algo_run → motor_set_diff
 *   更简洁，且通过预取 ops 指针避免每次字符串查找的开销。
 *
 *   Bind 时机：在所有组件 (sensor/pid/motor) 注册完成后调用。
 *   Update 内部使用 efw_motor_set_diff_limited —— 自带速度限幅，比 follow_diff 更安全。
 */

#ifndef EFW_SENSOR_LINE_TRACKING_H
#define EFW_SENSOR_LINE_TRACKING_H

#include "efw/core/common.h"
#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/device/actuator.h"

/**
 * @brief 循迹传感器数据结构
 * @field count  实际使用的通道数 (≤ EFW_LINE_TRACKING_MAX_CHANNELS)
 * @field value[] 各通道读数。模拟量=ADC值(0~65535), 数字量=0/1
 */
typedef struct {
    uint8_t count;
    uint16_t value[EFW_LINE_TRACKING_MAX_CHANNELS];
} efw_line_tracking_data_t;

/**
 * @brief 巡线跟随器 —— 将循迹控制所需的所有组件绑定为一个对象
 *
 * 使用前先调用 efw_line_follower_bind() 绑定各组件 (通过名称查找并缓存 ops 指针)，
 * 然后每周期调用 efw_line_follower_update() 执行完整的感知→决策→执行链路。
 *
 * 所有字段由 bind 填充，用户不应手动修改。
 *
 * @field sensor       [内部] 传感器 ops 指针 (bind 时缓存)
 * @field pid          [内部] PID 算法 ops 指针
 * @field left_motor   [内部] 左电机执行器 ops 指针
 * @field right_motor  [内部] 右电机执行器 ops 指针
 * @field weights      权重数组指针 (bind 时传入，必须是静态/全局数组)
 * @field active_value 数字循迹的"检测到线"电平值 (0 或 1)
 * @field base_speed   基础巡航速度
 * @field min_speed    最小速度限制 (≥0 防止反转)
 * @field max_speed    最大速度限制
 * @field dt           控制周期 (秒)
 */
typedef struct {
    const efw_sensor_ops_t *sensor;       /**< 传感器 ops (bind 时缓存) */
    const efw_algo_ops_t *pid;            /**< PID ops (bind 时缓存) */
    const efw_actuator_ops_t *left_motor; /**< 左电机 ops (bind 时缓存) */
    const efw_actuator_ops_t *right_motor;/**< 右电机 ops (bind 时缓存) */
    const float *weights;                 /**< 权重数组 (bind 时传入) */
    uint16_t active_value;                /**< 数字循迹有效电平 (0 或 1) */
    uint8_t binary_mode;                  /**< 1=数字二值误差, 0=模拟加权误差 */
    float base_speed;                     /**< 基础巡航速度 */
    float min_speed;                      /**< 最小速度限制 */
    float max_speed;                      /**< 最大速度限制 */
    float dt;                             /**< 控制周期 (秒) */
} efw_line_follower_t;

/**
 * @brief 巡线跟随器配置 —— 推荐使用，避免 bind 参数过长
 */
typedef struct {
    const char *sensor_name;
    const char *pid_name;
    const char *left_motor;
    const char *right_motor;
    const float *weights;
    float base_speed;
    float min_speed;
    float max_speed;
    float dt;
    uint16_t active_value;
    uint8_t binary_mode;
} efw_line_follower_config_t;

/* ====== 传感器读取 ====== */

efw_status_t efw_line_tracking_read(const char *name, efw_line_tracking_data_t *out);

/* ====== 模拟量算法 ====== */

/**
 * @brief 加权误差 (模拟量) —— 以亮度为权重的质心位置
 *
 * error = Σ(weights[i] × value[i]) / Σ(value[i])
 * 正值=黑线偏右, 负值=偏左, 0=居中
 */
float efw_line_tracking_error_weighted(const efw_line_tracking_data_t *data, const float *weights);

/* ====== 数字量算法 ====== */

/**
 * @brief 激活通道掩码 —— 返回一个位掩码表示哪些通道检测到了线
 *
 * 遍历所有通道，若 value[i] == active_value → mask 的第 i 位置 1。
 * 最多支持 16 通道 (uint16_t 共 16 位)。
 *
 * @param data         传感器数据
 * @param active_value "检测到线"的电平值 (0 或 1)
 * @return 位掩码 (bit i = 通道 i 检测到线)
 *
 * 示例：active_value=1, data={1, 0, 1, 0, 0} → mask = 0b00101 = 5
 */
uint16_t efw_line_tracking_active_mask(const efw_line_tracking_data_t *data, uint16_t active_value);

/**
 * @brief 二值化偏差 (数字量) —— 所有检测到线的通道的平均偏差
 *
 * 只对"检测到线" (value[i] == active_value) 的通道取 error_table[i] 的平均。
 * 与加权误差不同——这里不关心信号强度，只关心"有没有线"。
 *
 * @param data        传感器数据
 * @param error_table 各通道预定义偏差值数组 (如 {-2,-1,0,1,2})
 * @param active_value "检测到线"的电平值
 * @return 平均偏差 (0=居中, 正=偏右, 负=偏左)。无信号时返回 0。
 */
float efw_line_tracking_error_binary(const efw_line_tracking_data_t *data,
                                     const float *error_table, uint16_t active_value);

/* ====== 高层 API ====== */

/**
 * @brief 一步循迹差速控制 (低频/简单场景 API，推荐迁移到 efw_line_follower_*)
 *
 * 内部执行：read → error_weighted → PID → motor_set_diff
 * 使用 set_diff (无速度限制)。
 */
efw_status_t efw_line_tracking_follow_diff(const char *sensor_name, const char *pid_name,
                                           const char *left_motor, const char *right_motor,
                                           const float *weights, float base_speed, float dt,
                                           float *out_error, float *out_turn);

/**
 * @brief 配置式绑定巡线跟随器 ★ 推荐 API
 *
 * 初始化阶段按名称查找一次并缓存 ops 指针；控制循环调用 update 时不再查字符串。
 */
efw_status_t efw_line_follower_bind_config(efw_line_follower_t *follower,
                                           const efw_line_follower_config_t *config);

/**
 * @brief 绑定巡线跟随器 ★ 新版推荐 API
 *
 * 一次性查找并缓存所有组件的 ops 指针，后续 update 时省去字符串查找开销。
 *
 * 必须在所有组件 (sensor/pid/motor) 注册完成后调用。
 *
 * @param follower     巡线跟随器对象 (未初始化，本函数填充)
 * @param sensor_name  传感器注册名称
 * @param pid_name     PID 算法注册名称
 * @param left_motor   左电机注册名称
 * @param right_motor  右电机注册名称
 * @param weights      权重数组指针 (必须为静态/全局生存期)
 * @param base_speed   基础巡航速度
 * @param min_speed    最小速度限制
 * @param max_speed    最大速度限制
 * @param dt           控制周期 (秒)
 * @return EFW_OK 全部绑定成功
 */
efw_status_t efw_line_follower_bind(efw_line_follower_t *follower,
                                    const char *sensor_name, const char *pid_name,
                                    const char *left_motor, const char *right_motor,
                                    const float *weights, float base_speed,
                                    float min_speed, float max_speed, float dt);

/**
 * @brief 更新巡线跟随器 ★ 每控制周期调用
 *
 * 内部使用缓存的 ops 指针执行完整链路：
 *   read → error_weighted → PID → motor_set_diff_limited (带限速)
 *
 * 比 follow_diff 更高效 (无字符串查找) 且更安全 (有限速)。
 *
 * @param follower  已绑定的巡线跟随器
 * @param out_error 输出参数：本次加权误差值 (可 NULL)
 * @param out_turn  输出参数：本次 PID 输出的转向量 (可 NULL)
 * @return EFW_OK 成功
 */
efw_status_t efw_line_follower_update(efw_line_follower_t *follower, float *out_error, float *out_turn);

#endif
