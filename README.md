# Embedded Framework (EFW)

EFW 是一个面向裸机和轻量 RTOS 的嵌入式 C 框架，可直接作为库集成到 STM32、ESP32、MSPM0 等工程中。

## 目标
- 无动态内存、无标准库重依赖、无操作系统依赖
- HAL、通信、模块、传感器、算法、状态机统一注册和按名称调用
- 上层业务只依赖 EFW API，底层 BSP 通过回调适配芯片 SDK
- 同类不同型号设备可以通过相同类型和不同实例名接入

## 分层
1. HAL 适配层：GPIO/I2C/SPI/UART/TIMER/PWM/ADC 等芯片外设封装
2. 通信层：UART/CAN/I2C/SPI/ETH 等通信实例，可绑定到底层 HAL
3. 设备层：传感器等驱动对象，可绑定 HAL 或通信实例
4. 算法层：PID、滑动均值等可注册算法
5. 模块层：驱动、服务、应用模块生命周期管理
6. 应用层：初始化注册、循环调度、业务编排

## 目录
- `include/efw/efw.h`：聚合入口头文件，应用层优先包含它
- `include/efw/core/`：基础类型、状态码和容量配置
- `include/efw/hal/`：芯片外设抽象接口
- `include/efw/comm/`：UART/CAN/I2C/SPI/ETH 等通信接口
- `include/efw/device/`：传感器等设备接口
- `include/efw/algorithm/`：算法注册表和内置算法
- `include/efw/module/`：模块生命周期接口
- `include/efw/state/`：状态机接口
- `src/`：库源码，按功能分层，可按需加入 Keil、STM32CubeIDE、ESP-IDF 或 CMake 工程
- `application/`：接近真实工程结构的应用示例
- `docs/`：设计说明

## 快速接入
1. 把 `include/` 加入头文件路径。
2. 按需把 `src/**/*.c` 加入工程编译。
3. 在系统启动后调用 `efw_init()`。
4. 注册 BSP HAL、通信对象、传感器、算法和模块。
5. 在主循环或定时任务里调用 `efw_sensor_read()`、`efw_algo_run()`、`efw_module_poll_all()` 等接口。

## Keil 接入
Keil 不需要 CMake，直接以源码库方式接入：

1. 在 `Options for Target > C/C++ > Include Paths` 添加 `framework/include`。
2. 新建一个 `EFW` Group。
3. 至少加入核心初始化文件，再按功能加入对应源码：
```text
必选：src/core/init.c
HAL：src/hal/hal_registry.c
COMM：src/comm/comm_registry.c
MODULE：src/module/module_registry.c
SENSOR：src/device/sensor_registry.c
循迹中间层：src/device/sensor/line_tracking.c
IMU 中间层：src/device/sensor/imu.c
编码器中间层：src/device/sensor/encoder.c
超声中间层：src/device/sensor/ultrasonic.c
自定义传感器中间层：src/device/sensor/custom.c
ACTUATOR：src/device/actuator_registry.c
电机便捷层：src/device/actuator/motor.c
ALGORITHM 注册表：src/algorithm/algorithm_registry.c
PID：src/algorithm/control/pid.c
滑动均值：src/algorithm/filter/moving_average.c
STATE：src/state/state_machine_registry.c
```
4. 应用代码包含 `#include "efw/efw.h"`。
5. 在 `main()` 初始化阶段调用 `efw_init()`，然后注册平台 HAL 和业务模块。

如果裁剪某个功能，需要在 Keil 的 `C/C++ > Define` 中同步关闭对应宏，例如 `EFW_ENABLE_COMM=0`。

## CMake 构建
CMake 只用于主机侧编译验证或支持 CMake 的工程，不是裸机接入必需项。

```bash
cmake -S . -B build -DEFW_BUILD_APPLICATIONS=ON
cmake --build build
```

选择性编译示例：

```bash
cmake -S . -B build-min \
  -DEFW_ENABLE_COMM=OFF \
  -DEFW_ENABLE_MODULE=OFF \
  -DEFW_ENABLE_STATE_MACHINE=OFF
cmake --build build-min
```

## 配置
默认功能开关和容量在 `include/efw/core/config.h` 中定义，可在编译参数里覆盖：

```c
#define EFW_ENABLE_HAL 1
#define EFW_ENABLE_COMM 1
#define EFW_ENABLE_MODULE 1
#define EFW_ENABLE_SENSOR 1
#define EFW_ENABLE_SENSOR_LINE_TRACKING 1
#define EFW_ENABLE_SENSOR_IMU 1
#define EFW_ENABLE_SENSOR_ENCODER 1
#define EFW_ENABLE_SENSOR_ULTRASONIC 1
#define EFW_ENABLE_SENSOR_CUSTOM 1
#define EFW_ENABLE_ACTUATOR 1
#define EFW_ENABLE_ACTUATOR_MOTOR 1
#define EFW_ENABLE_ALGORITHM 1
#define EFW_ENABLE_ALGO_PID 1
#define EFW_ENABLE_ALGO_MOVING_AVG 1
#define EFW_ENABLE_STATE_MACHINE 1
```

```c
#define EFW_MAX_HALS 16
#define EFW_MAX_COMMS 16
#define EFW_MAX_MODULES 32
#define EFW_MAX_SENSORS 32
#define EFW_LINE_TRACKING_MAX_CHANNELS 8
#define EFW_MAX_ACTUATORS 16
#define EFW_MAX_ALGOS 16
#define EFW_MAX_STATE_MACHINES 8
```

## 当前能力
- HAL 注册、查找和便捷读写
- COMM 注册、HAL 绑定和便捷收发
- MODULE 注册、单个/全部初始化启动轮询
- SENSOR 注册、HAL/COMM 绑定和便捷读取
- 常用传感器中间层：循迹、IMU、编码器、超声波
- 自定义传感器中间层：未知传感器使用 `EFW_SENSOR_CUSTOM` 和 `efw_custom_sensor_read()` 接入
- ACTUATOR 注册、HAL/COMM 绑定、使能/失能和写入控制
- 电机便捷层：`efw_motor_set_speed()`、`efw_motor_set_diff()`、`efw_motor_stop()`
- ALGORITHM 注册和运行
- 内置 PID 与滑动均值算法
- 循迹便捷控制：`efw_line_tracking_follow_diff()` 一次完成读取、误差、PID、左右电机差速输出
- STATE MACHINE 注册和查找

## 示例
- `application/line_tracking_car/`：基础 5 路循迹小车应用结构，拆分为平台适配、组件注册、应用逻辑和入口文件。

## Application 结构
应用示例不再写成单文件，而是拆成：

```text
application/line_tracking_car/
  app_board_config.h   板级参数：引脚、PWM 通道、速度范围、控制周期
  app_platform.c        底层适配回调、HAL/SENSOR/ACTUATOR 注册
  app_components.c      算法和可复用组件注册
  app_line_tracking_car.c 应用控制逻辑
  main.c                启动入口
```

真实项目迁移时，先在 `app_board_config.h` 设置引脚、PWM 通道、速度范围等参数，再在 `app_platform.c` 中把 mock 读写替换成 STM32 HAL、ESP-IDF 或 MSPM0 DriverLib 调用。

优化后的循迹循环可以写成一行：

```c
efw_line_tracking_follow_diff("line_sensor_5ch", "line_pid", "left_motor", "right_motor", weights, 45.0f, 0.001f, 0, 0);
```
