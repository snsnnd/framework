/**
 * @file    efw.h
 * @brief   EFW 框架统一入口头文件
 *
 * 使用者只需要 #include "efw/efw.h" 即可引入整个框架的所有 API。
 *
 * 【条件编译机制】
 *   本文件不无条件 include 所有子模块，而是根据 config.h 中的 EFW_ENABLE_*
 *   宏决定引入哪些头文件。例如：
 *     - 若 EFW_ENABLE_COMM=0，则 comm.h 不会被 include，COMM 所有 API 不可见
 *     - 若 EFW_ENABLE_ALGO_PID=0，则 pid.h 不会被 include
 *   这样做的好处：
 *     ① 减小编译产物（未启用的模块根本不出现在翻译单元中）
 *     ② 编译期即可发现误用（若禁用了 COMM 却试图调用 efw_comm_send，链接报错）
 *     ③ 方便按项目需求裁剪框架
 *
 * 【唯一对外 API】
 *   本文件是框架唯一的 public API 面。用户代码不应直接 include 子目录中的
 *   任何头文件（如 efw/hal/hal.h）——所有公共类型和函数都通过本文件间接暴露。
 *
 * 【初始化入口】
 *   efw_init() 是本文件中声明的唯一函数，它会按依赖顺序依次初始化
 *   所有已启用的注册表。
 */

#ifndef EFW_H
#define EFW_H

/* 基础类型和配置 — 始终引入，无开关控制 */
#include "efw/core/common.h"
#include "efw/core/config.h"

/* 以下各层按 EFW_ENABLE_* 开关条件引入 */

#if EFW_ENABLE_HAL
#include "efw/hal/hal.h"            /**< HAL 硬件抽象层 (GPIO/UART/SPI/I2C/ADC/PWM/TIMER) */
#endif

#if EFW_ENABLE_COMM
#include "efw/comm/comm.h"          /**< COMM 通信层 (UART/CAN/I2C/SPI/ETH 协议封装) */
#endif

#if EFW_ENABLE_MODULE
#include "efw/module/module.h"      /**< Module 模块生命周期 (init→start→poll→stop) */
#endif

#if EFW_ENABLE_SENSOR
#include "efw/device/sensor.h"      /**< Sensor 传感器设备 (循迹/IMU/编码器/超声波) */
#if EFW_ENABLE_SENSOR_LINE_TRACKING
#include "efw/device/sensor/line_tracking.h"
#endif
#if EFW_ENABLE_SENSOR_IMU
#include "efw/device/sensor/imu.h"
#endif
#if EFW_ENABLE_SENSOR_ENCODER
#include "efw/device/sensor/encoder.h"
#endif
#if EFW_ENABLE_SENSOR_ULTRASONIC
#include "efw/device/sensor/ultrasonic.h"
#endif
#if EFW_ENABLE_SENSOR_CUSTOM
#include "efw/device/sensor/custom.h"
#endif
#endif

#if EFW_ENABLE_ACTUATOR
#include "efw/device/actuator.h"    /**< Actuator 执行器 (电机/舵机/继电器/LED) */
#if EFW_ENABLE_ACTUATOR_MOTOR
#include "efw/device/actuator/motor.h"
#endif
#endif

#if EFW_ENABLE_ALGORITHM
#include "efw/algorithm/registry.h"  /**< Algorithm 算法注册表 */
#endif

/* 算法实现只在注册表启用 + 对应算法开关启用时才引入 */
#if EFW_ENABLE_ALGO_PID || EFW_ENABLE_ALGO_MOVING_AVG
#include "efw/algorithm/algorithms.h" /**< 内置算法分发 (→pid.h / →moving_average.h) */
#endif

#if EFW_ENABLE_STATE_MACHINE
#include "efw/state/state_machine.h" /**< StateMachine 状态机 */
#endif

/**
 * @brief EFW 框架统一初始化
 *
 * 按依赖顺序初始化所有已启用的注册表：
 *   HAL → COMM → MODULE → SENSOR → ACTUATOR → ALGORITHM → STATE_MACHINE
 *
 * 只有被 EFW_ENABLE_*=1 启用的注册表才会被初始化，禁用的自动跳过。
 *
 * @return EFW_OK 全部成功, 否则返回第一个失败注册表的错误码
 */
efw_status_t efw_init(void);

#endif
