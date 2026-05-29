/**
 * @file    actuator.h
 * @brief   Actuator (执行器设备层) 注册表接口
 *
 * 本层与 Sensor (传感器) 对称——Sensor 负责"读"(感知)，Actuator 负责"写"(执行)。
 *
 * =========================================================================
 * 可注册的执行器类型 (efw_actuator_type_t)
 * =========================================================================
 *
 *   ┌─────────────────────┬──────────────────────────────────────────┐
 *   │ EFW_ACTUATOR_MOTOR   │ 电机 (直流有刷/无刷/步进)                 │
 *   │ EFW_ACTUATOR_SERVO   │ 舵机 (PWM 控制角度的伺服电机)              │
 *   │ EFW_ACTUATOR_RELAY   │ 继电器 (开关量控制，如电磁阀/加热器)       │
 *   │ EFW_ACTUATOR_LED     │ LED (亮度控制、状态指示灯)                 │
 *   │ EFW_ACTUATOR_CUSTOM  │ 自定义执行器 (泵、蜂鸣器、电磁铁等)       │
 *   └─────────────────────┴──────────────────────────────────────────┘
 *
 * =========================================================================
 * 执行器操作接口
 * =========================================================================
 *
 *   每个执行器支持 4 种操作：
 *     init    — 初始化 (配置 PWM、GPIO 等)
 *     enable  — 使能 (上电、使能驱动器、解锁)
 *     disable — 禁用 (断电、禁用驱动器、锁定)
 *     write   — 写入控制指令 (设置速度、角度、亮度等)
 *
 *   enable/disable 的设计动机：
 *     很多执行器不只是"设置输出"——它们有独立的使能/禁用逻辑。
 *     例如：电机驱动器的 EN 引脚、舵机的电源开关。
 *     enable/disable 与控制量 write 分离，使得安全逻辑更清晰。
 *
 * =========================================================================
 * 命令结构体
 * =========================================================================
 *
 *   efw_actuator_cmd_t  — 通用命令 (只有一个 value 字段，适合 LED/继电器)
 *   efw_motor_cmd_t     — 电机专用命令 (speed=速度, direction=方向)
 *
 *   这两个是框架内置的命令格式。用户可以通过 write 的 void* cmd 参数
 *   传入任意自定义结构体（write 回调内部知道如何解包）。
 *
 * =========================================================================
 * IO 绑定机制 (与 Sensor 一致)
 * =========================================================================
 *
 *   每个执行器可以绑定到一个 HAL (如 PWM 输出) 或一个 COMM (如 CAN 总线电机)，
 *   也可以都不绑（纯软件虚拟执行器）。
 *   注册时框架校验 hal_name/comm_name 引用的 HAL/COMM 是否已存在。
 *
 * =========================================================================
 * 使用示例
 * =========================================================================
 *
 *   // 注册一个 PWM 舵机
 *   efw_actuator_ops_t servo = {
 *       .name = "steering_servo",
 *       .type = EFW_ACTUATOR_SERVO,
 *       .hal_name = "pwm_ch3",      // 绑定到 PWM HAL
 *       .ctx = &my_servo_ctx,
 *       .init = servo_init,         // 配置 PWM 频率和初始角度
 *       .enable = servo_enable,     // 使能 PWM 输出
 *       .disable = servo_disable,   // 禁用 PWM 输出
 *       .write = servo_set_angle    // 将角度转换为 PWM 占空比
 *   };
 *   efw_actuator_register(&servo);
 *
 *   // 使用时
 *   float angle = 90.0f;
 *   efw_actuator_enable("steering_servo");
 *   efw_actuator_write("steering_servo", &angle);
 */

#ifndef EFW_ACTUATOR_H
#define EFW_ACTUATOR_H

#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include "efw/comm/comm.h"

/**
 * @brief 执行器类型枚举
 */
typedef enum {
    EFW_ACTUATOR_MOTOR  = 0, /**< 电机：直流有刷/无刷/步进电机，控制转速/位置/力矩 */
    EFW_ACTUATOR_SERVO,      /**< 舵机：PWM 伺服电机，控制角度 (通常 0~180°) */
    EFW_ACTUATOR_RELAY,      /**< 继电器：开关量控制 (电磁阀、加热器、水泵等) */
    EFW_ACTUATOR_LED,        /**< LED：亮度控制 (PWM 调光) 或状态指示 (开关) */
    EFW_ACTUATOR_CUSTOM      /**< 自定义执行器：蜂鸣器、电磁铁、泵等 */
} efw_actuator_type_t;

/**
 * @brief 通用执行器命令 (适合 LED、继电器等单值执行器)
 *
 * @field value 控制值。含义取决于执行器类型：
 *               LED → 亮度 (0.0=灭, 1.0=全亮)，继电器 → 0.0=断开, 1.0=闭合
 */
typedef struct {
    float value;            /**< 通用控制值 */
} efw_actuator_cmd_t;

/**
 * @brief 电机专用命令
 *
 * @field speed     速度值 (含义由实现定义：如 m/s、RPM、-1.0~1.0 相对值)
 * @field direction 方向：正值=正转/前进, 负值=反转/后退, 0=停止
 */
typedef struct {
    float speed;            /**< 电机速度 */
    float direction;        /**< 电机方向 (正=前进, 负=后退) */
} efw_motor_cmd_t;

/**
 * @brief 执行器操作接口结构体
 *
 * @field name     全局唯一名称 (如 "left_motor", "steering_servo", "pump_relay")
 * @field type     执行器类型 (efw_actuator_type_t)
 * @field hal_name 绑定的 HAL 名称 (可空，如 "pwm_ch1")，注册时校验存在性
 * @field comm_name绑定的 COMM 名称 (可空，如 "motor_can")，注册时校验存在性
 *                 hal_name 和 comm_name 至少填一个 (纯虚拟执行器可都不填)
 * @field ctx      用户私有上下文 (如 PWM 通道号、GPIO 引脚、CAN 节点 ID)
 * @field init     初始化回调 (可空)
 *                 典型操作：配置 PWM 频率/分辨率、设置 GPIO 为输出
 * @field enable   使能回调 (可空)
 *                 典型操作：拉高 EN 引脚、启动 PWM 输出、发送使能帧
 * @field disable  禁用回调 (可空)
 *                 典型操作：拉低 EN 引脚、停止 PWM、发送禁用帧、进入安全态
 * @field write    写入控制指令回调 (必填，注册时校验)
 *                 cmd 指向命令结构体 (efw_actuator_cmd_t / efw_motor_cmd_t / 自定义)
 */
typedef struct {
    const char *name;           /**< 全局唯一名称 */
    efw_actuator_type_t type;   /**< 执行器类型 */
    const char *hal_name;       /**< 绑定的 HAL 名称 (可空) */
    const char *comm_name;      /**< 绑定的 COMM 名称 (可空) */
    void *ctx;                  /**< 用户私有上下文 */
    efw_status_t (*init)(void *ctx);            /**< 初始化回调 (可空) */
    efw_status_t (*enable)(void *ctx);          /**< 使能回调 (可空) */
    efw_status_t (*disable)(void *ctx);         /**< 禁用回调 (可空) */
    efw_status_t (*write)(void *ctx, const void *cmd); /**< 写入指令回调 (必填) */
} efw_actuator_ops_t;

/* ====== 执行器注册表 API ====== */

efw_status_t efw_actuator_registry_init(void);
efw_status_t efw_actuator_registry_init_pool(const efw_actuator_ops_t **pool, size_t capacity);
efw_status_t efw_actuator_register(const efw_actuator_ops_t *ops);
efw_status_t efw_actuator_get(const char *name, const efw_actuator_ops_t **out_ops);
size_t efw_actuator_count_by_type(efw_actuator_type_t type);
efw_status_t efw_actuator_bind_hal(const char *actuator_name, const efw_hal_ops_t **out_hal);
efw_status_t efw_actuator_bind_comm(const char *actuator_name, const efw_comm_ops_t **out_comm);
efw_status_t efw_actuator_init_device(const char *name);
efw_status_t efw_actuator_enable(const char *name);
efw_status_t efw_actuator_disable(const char *name);
efw_status_t efw_actuator_write(const char *name, const void *cmd);

#endif
