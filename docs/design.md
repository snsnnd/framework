# EFW 设计说明

## 1. 裸机可移植约束
- 核心库不分配堆内存。
- 核心库不创建线程、任务、定时器或中断。
- 所有实例由用户静态定义，并通过注册表挂载。
- 芯片 SDK 只出现在 BSP 回调里，不进入框架核心。

## 2. 目录分层
- `include/efw/efw.h` 是应用层聚合入口。
- `include/efw/core/` 放公共类型和配置。
- `include/efw/hal/` 放底层外设抽象。
- `include/efw/comm/` 放通信抽象。
- `include/efw/device/` 放传感器等设备抽象。
- `include/efw/algorithm/` 放算法注册和内置算法。
- `include/efw/module/` 放模块生命周期。
- `include/efw/state/` 放状态机。

## 3. 初始化顺序
1. 调用 `efw_init()` 清空所有注册表。
2. 注册 HAL，例如 `adc1`、`uart1`、`i2c1`。
3. 注册 COMM，例如 `dbg_uart` 绑定 `uart1`。
4. 注册 SENSOR，例如 `line_sensor_5ch` 绑定 `line_input`。
5. 注册 ACTUATOR，例如 `left_motor` 绑定 PWM HAL。
6. 注册 ALGORITHM，例如 `motor_pid`。
7. 注册 MODULE，并在主循环中轮询。

## 4. 绑定规则
- `efw_comm_ops_t.hal_name` 指向一个已注册 HAL。
- `efw_sensor_ops_t.hal_name` 指向一个已注册 HAL。
- `efw_sensor_ops_t.comm_name` 指向一个已注册 COMM。
- `efw_actuator_ops_t.hal_name` 指向一个已注册 HAL。
- `efw_actuator_ops_t.comm_name` 指向一个已注册 COMM。
- 注册时会检查绑定目标是否存在，避免运行后才暴露配置错误。

## 5. 传感器注册表
- 统一接口：`init/read`。
- 关键字段：`name/type/channel_count/hal_name/comm_name`。
- 示例：4 路循迹和 8 路循迹都使用 `EFW_SENSOR_LINE_TRACKING`，通过 `channel_count` 区分。

## 6. 传感器中间层
- 中间层只定义通用数据结构和类型化读取 API，不包含具体芯片驱动。
- 应用层调用 `efw_line_tracking_read()`、`efw_imu_read()`、`efw_encoder_read()`、`efw_ultrasonic_read()`。
- 底层驱动仍通过 `efw_sensor_ops_t.read` 适配，只需要把 MCU/芯片数据转换成中间层数据结构。
- 例如 MPU6050、ICM42688 都可以输出 `efw_imu_data_t`，应用层不用关心具体型号。

## 7. 算法注册表
- 算法通过 `efw_algo_ops_t` 挂载。
- 当前内置 PID 和滑动均值，源码分别在 `src/algorithm/control/pid.c` 与 `src/algorithm/filter/moving_average.c`。
- 应用层通过 `efw_algo_run("motor_pid", &input, &output)` 调用。

## 8. 执行器注册表
- 统一接口：`init/enable/disable/write`。
- 支持电机、舵机、继电器、LED 和自定义执行器。
- 电机可使用 `efw_motor_cmd_t` 作为命令输入，也可以使用用户自定义命令结构。

## 9. 模块注册表
- 模块用于管理驱动、服务和应用逻辑生命周期。
- 支持 `init/start/stop/poll`。
- 主循环可直接调用 `efw_module_poll_all()`。

## 10. 平台迁移建议
- STM32：HAL 回调中调用 STM32 HAL/LL，例如 `HAL_UART_Transmit`、`HAL_ADC_GetValue`。
- ESP32：HAL 回调中调用 ESP-IDF driver，例如 `uart_write_bytes`、`i2c_master_transmit`。
- MSPM0：HAL 回调中调用 DriverLib，例如 `DL_UART_transmitDataBlocking`。
- 对上层应用来说，平台差异只体现在注册的 HAL 回调实现。

## 11. Keil 工程接入
- Keil 不使用 CMake 时，直接把 `include` 加入 Include Paths。
- 必选源码只有 `src/core/init.c`。
- 需要 HAL 时加入 `src/hal/hal_registry.c` 并保持 `EFW_ENABLE_HAL=1`。
- 需要 COMM 时加入 `src/comm/comm_registry.c` 并保持 `EFW_ENABLE_COMM=1`。
- 需要 SENSOR 时加入 `src/device/sensor_registry.c` 并保持 `EFW_ENABLE_SENSOR=1`。
- 需要循迹中间层时加入 `src/device/sensor/line_tracking.c` 并保持 `EFW_ENABLE_SENSOR_LINE_TRACKING=1`。
- 需要 IMU 中间层时加入 `src/device/sensor/imu.c` 并保持 `EFW_ENABLE_SENSOR_IMU=1`。
- 需要编码器中间层时加入 `src/device/sensor/encoder.c` 并保持 `EFW_ENABLE_SENSOR_ENCODER=1`。
- 需要超声中间层时加入 `src/device/sensor/ultrasonic.c` 并保持 `EFW_ENABLE_SENSOR_ULTRASONIC=1`。
- 需要自定义传感器中间层时加入 `src/device/sensor/custom.c` 并保持 `EFW_ENABLE_SENSOR_CUSTOM=1`。
- 需要 ACTUATOR 时加入 `src/device/actuator_registry.c` 并保持 `EFW_ENABLE_ACTUATOR=1`。
- 需要电机便捷层时加入 `src/device/actuator/motor.c` 并保持 `EFW_ENABLE_ACTUATOR_MOTOR=1`。
- 需要算法注册表时加入 `src/algorithm/algorithm_registry.c` 并保持 `EFW_ENABLE_ALGORITHM=1`。
- 需要 PID 时加入 `src/algorithm/control/pid.c` 并保持 `EFW_ENABLE_ALGO_PID=1`。
- 需要滑动均值时加入 `src/algorithm/filter/moving_average.c` 并保持 `EFW_ENABLE_ALGO_MOVING_AVG=1`。
- 不用的功能不要加入 `.c` 文件，同时在 Keil Define 中设置对应 `EFW_ENABLE_* = 0`。

## 12. Application 目录
- `application/` 用来放具体应用工程代码，不属于框架核心库。
- `app_board_config.h` 放板级参数，例如 GPIO 端口/引脚、PWM 定时器通道、速度范围、控制周期。
- `app_platform.c` 放底层适配回调和硬件相关注册，例如 ADC、PWM、电机 GPIO。
- `app_components.c` 放算法、传感器、执行器等组件注册。
- `app_xxx.c` 放应用层业务逻辑。
- 未知传感器使用 `EFW_SENSOR_CUSTOM` 注册，应用层可通过 `efw_custom_sensor_read()` 或自行定义新的中间层头文件读取。
