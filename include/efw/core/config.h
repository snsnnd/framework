/**
 * @file    config.h
 * @brief   EFW 框架编译期配置 —— 模块开关 + 容量上限
 *
 * 本文件提供两级配置：
 *
 * 【第1级：模块开关 EFW_ENABLE_* (值为 1=启用, 0=禁用)】
 *   控制整个功能模块是否编译。禁用后相关代码通过 #if 被完全剔除，
 *   不占用 ROM/RAM，也不产生任何运行时开销。
 *   适用于资源极度紧张的 MCU（如 STM32F0 仅 16KB Flash），
 *   可只启用 HAL+SENSOR+ALGO_PID，禁用 COMM/ACTUATOR/STATE_MACHINE。
 *
 *   各开关含义：
 *     EFW_ENABLE_HAL            → HAL (硬件抽象层) 注册表
 *     EFW_ENABLE_COMM           → COMM (通信层) 注册表
 *     EFW_ENABLE_MODULE         → Module (模块生命周期) 注册表
 *     EFW_ENABLE_SENSOR         → Sensor (传感器) 注册表
 *     EFW_ENABLE_ACTUATOR       → Actuator (执行器) 注册表 — NEW
 *     EFW_ENABLE_ALGORITHM      → Algorithm (算法) 注册表
 *     EFW_ENABLE_ALGO_PID       → PID 控制器算法实现
 *     EFW_ENABLE_ALGO_MOVING_AVG → 滑动均值滤波算法实现
 *     EFW_ENABLE_STATE_MACHINE  → StateMachine (状态机) 注册表
 *
 *   依赖关系（被依赖方禁用 → 依赖方自动失效）：
 *     COMM 依赖 HAL    → 若 EFW_ENABLE_HAL=0，COMM 注册时 hal_name 校验返回错误
 *     SENSOR 依赖 HAL/COMM → 同上
 *     ACTUATOR 依赖 HAL/COMM → 同上
 *
 * 【第2级：容量上限 EFW_MAX_* (正整数)】
 *   控制每个注册表最多可注册多少个实例。更大的值 → 更多 RAM 占用。
 *   所有上限均可通过编译器 -D 选项覆写，例如：
 *     gcc -DEFW_MAX_SENSORS=64 -DEFW_MAX_HALS=8 ...
 *
 * 内存占用估算（32 位 ARM，指针 4 字节）：
 *   全部使用默认值时 ≈ (16+16+32+32+16+16+8) * 4 = 544 字节
 *   （仅指针数组本身，不含用户定义的 ops 结构体和上下文数据）
 */

#ifndef EFW_CONFIG_H
#define EFW_CONFIG_H

/* ==================================================================
 *  第1级：模块编译开关 (1=启用, 0=禁用)
 *  通过编译器 -D 覆写，例如 -DEFW_ENABLE_COMM=0 禁用通信层
 * ================================================================== */

#ifndef EFW_ENABLE_HAL
#define EFW_ENABLE_HAL 1            /**< HAL 硬件抽象层开关 */
#endif

#ifndef EFW_ENABLE_COMM
#define EFW_ENABLE_COMM 1           /**< COMM 通信层开关 (依赖 HAL) */
#endif

#ifndef EFW_ENABLE_MODULE
#define EFW_ENABLE_MODULE 1         /**< Module 模块生命周期开关 */
#endif

#ifndef EFW_ENABLE_SENSOR
#define EFW_ENABLE_SENSOR 1         /**< Sensor 传感器设备开关 (依赖 HAL/COMM) */
#endif

#ifndef EFW_ENABLE_SENSOR_LINE_TRACKING
#define EFW_ENABLE_SENSOR_LINE_TRACKING 1
#endif

#ifndef EFW_ENABLE_SENSOR_IMU
#define EFW_ENABLE_SENSOR_IMU 1
#endif

#ifndef EFW_ENABLE_SENSOR_ENCODER
#define EFW_ENABLE_SENSOR_ENCODER 1
#endif

#ifndef EFW_ENABLE_SENSOR_ULTRASONIC
#define EFW_ENABLE_SENSOR_ULTRASONIC 1
#endif

#ifndef EFW_ENABLE_SENSOR_CUSTOM
#define EFW_ENABLE_SENSOR_CUSTOM 1
#endif

#ifndef EFW_ENABLE_ACTUATOR
#define EFW_ENABLE_ACTUATOR 1       /**< Actuator 执行器开关 (依赖 HAL/COMM) */
#endif

#ifndef EFW_ENABLE_ACTUATOR_MOTOR
#define EFW_ENABLE_ACTUATOR_MOTOR 1
#endif

#ifndef EFW_ENABLE_ALGORITHM
#define EFW_ENABLE_ALGORITHM 1      /**< Algorithm 算法注册表开关 */
#endif

#ifndef EFW_ENABLE_ALGO_PID
#define EFW_ENABLE_ALGO_PID 1       /**< PID 控制器算法实现开关 */
#endif

#ifndef EFW_ENABLE_ALGO_MOVING_AVG
#define EFW_ENABLE_ALGO_MOVING_AVG 1 /**< 滑动均值滤波算法实现开关 */
#endif

#ifndef EFW_ENABLE_ALGO_LOW_PASS
#define EFW_ENABLE_ALGO_LOW_PASS 1
#endif

#ifndef EFW_ENABLE_ALGO_RAMP
#define EFW_ENABLE_ALGO_RAMP 1
#endif

#ifndef EFW_ENABLE_ALGO_ENCODER_SPEED
#define EFW_ENABLE_ALGO_ENCODER_SPEED 1
#endif

#ifndef EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY
#define EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY 1
#endif

#ifndef EFW_ENABLE_STATE_MACHINE
#define EFW_ENABLE_STATE_MACHINE 1  /**< StateMachine 状态机注册表开关 */
#endif

#ifndef EFW_ENABLE_EVENT
#define EFW_ENABLE_EVENT 1
#endif

#ifndef EFW_ENABLE_SCHEDULER
#define EFW_ENABLE_SCHEDULER 1
#endif


/* ==================================================================
 *  第2级：各注册表最大容量
 *
 *  设计原则：
 *    - 所有注册表使用静态数组（编译期确定大小），不涉及 malloc
 *    - 容量越大 → 内存占用越大（每槽位一个指针，典型 4/8 字节）
 *    - 根据实际 MCU 的 RAM 大小和项目需求调整
 *    - 每个 #ifndef 允许编译器 -D 覆写
 * ================================================================== */

/**
 * @brief HAL 层最大注册数量 (默认 16)
 *
 * HAL 代表最底层的硬件外设抽象，如 UART1、I2C2、SPI1 等。
 * 一个中型项目通常需要 5~10 个 HAL 实例。
 */
#ifndef EFW_MAX_HALS
#define EFW_MAX_HALS 16
#endif

/**
 * @brief 通信层最大注册数量 (默认 16)
 *
 * COMM 在 HAL 之上封装通信协议（UART→协议帧，CAN→帧格式等）。
 * 通常每个 HAL 可能对应 0~2 个 COMM，所以与 HAL 容量相同。
 */
#ifndef EFW_MAX_COMMS
#define EFW_MAX_COMMS 16
#endif

/**
 * @brief 模块层最大注册数量 (默认 32)
 *
 * 模块是最上层的业务逻辑单元（驱动封装、后台服务、应用任务）。
 * 容量设为 HAL/COMM 的两倍，因为一个项目通常模块数量 > 硬件设备数量。
 */
#ifndef EFW_MAX_MODULES
#define EFW_MAX_MODULES 32
#endif

/**
 * @brief 传感器设备最大注册数量 (默认 32)
 *
 * 传感器包括循迹模块、IMU、编码器、超声波等。大型机器人项目可能达到 20+。
 */
#ifndef EFW_MAX_SENSORS
#define EFW_MAX_SENSORS 32
#endif

#ifndef EFW_LINE_TRACKING_MAX_CHANNELS
#define EFW_LINE_TRACKING_MAX_CHANNELS 8
#endif

/**
 * @brief 执行器最大注册数量 (默认 16)
 *
 * 执行器包括电机、舵机、继电器、LED 等。中等复杂度项目通常需要 4~12 个。
 */
#ifndef EFW_MAX_ACTUATORS
#define EFW_MAX_ACTUATORS 16
#endif

#ifndef EFW_MAX_TOPIC_SUBS
#define EFW_MAX_TOPIC_SUBS 8
#endif

/**
 * @brief 算法实例最大注册数量 (默认 16)
 *
 * 每个算法实例（如 "左轮PID"、"右轮PID"、"陀螺仪滤波"）占用一个槽位。
 * 注意：同一 PID 代码可以注册多个实例（不同 name/ctx/参数），各占一个槽位。
 */
#ifndef EFW_MAX_ALGOS
#define EFW_MAX_ALGOS 16
#endif

/**
 * @brief 状态机最大注册数量 (默认 8)
 *
 * 典型用途：主任务状态机、充电管理状态机、通信协议状态机等。
 * 状态机数量通常较少，8 个已覆盖大多数场景。
 */
#ifndef EFW_MAX_STATE_MACHINES
#define EFW_MAX_STATE_MACHINES 8
#endif

#ifndef EFW_MAX_SCHEDULER_TASKS
#define EFW_MAX_SCHEDULER_TASKS 16
#endif

#ifndef EFW_ERROR_HISTORY_SIZE
#define EFW_ERROR_HISTORY_SIZE 4
#endif

#ifndef EFW_EVENT_QUEUE_CAPACITY
#define EFW_EVENT_QUEUE_CAPACITY 8
#endif

#ifndef EFW_EVENT_ITEM_MAX_SIZE
#define EFW_EVENT_ITEM_MAX_SIZE 32
#endif

#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
_Static_assert(EFW_EVENT_ITEM_MAX_SIZE >= 4, "EFW_EVENT_ITEM_MAX_SIZE must be >= 4");
_Static_assert(EFW_EVENT_QUEUE_CAPACITY >= 1, "EFW_EVENT_QUEUE_CAPACITY must be >= 1");
_Static_assert(EFW_MAX_SCHEDULER_TASKS >= 1, "EFW_MAX_SCHEDULER_TASKS must be >= 1");
#if EFW_ENABLE_COMM && !EFW_ENABLE_HAL
#error "EFW_ENABLE_COMM requires EFW_ENABLE_HAL"
#endif
#if EFW_ENABLE_SENSOR && !EFW_ENABLE_HAL
#error "EFW_ENABLE_SENSOR requires EFW_ENABLE_HAL"
#endif
#if EFW_ENABLE_ACTUATOR && !EFW_ENABLE_HAL
#error "EFW_ENABLE_ACTUATOR requires EFW_ENABLE_HAL"
#endif
#endif

#endif
