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
- `include/efw/app/`：通用 application runtime 和 manifest 类型
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
2. 推荐只加入 `src/efw_all.c`，由 `EFW_ENABLE_*` 宏决定实际编译哪些模块。
3. 在系统启动后调用 `efw_init()`。
4. 注册 BSP HAL、通信对象、传感器、算法和模块。
5. 在主循环或定时任务里调用 `efw_sensor_read()`、`efw_algo_run()`、`efw_module_poll_all()` 等接口。

## Keil 接入
Keil 不需要 CMake，直接以源码库方式接入：

1. 在 `Options for Target > C/C++ > Include Paths` 添加 `framework/include`。
2. 新建一个 `EFW` Group。
3. 推荐方式：只加入聚合入口。

```text
src/efw_all.c
```

如果不使用聚合入口，也可以按功能手动加入对应源码：
```text
必选：src/core/init.c
诊断：src/core/diagnostic.c
事件：src/core/event.c
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
低通滤波：src/algorithm/filter/low_pass.c
斜坡限速：src/algorithm/control/ramp.c
编码器测速：src/algorithm/estimator/encoder_speed.c
互补滤波姿态：src/algorithm/estimator/attitude_complementary.c
STATE：src/state/state_machine_registry.c
```
4. 应用代码包含 `#include "efw/efw.h"`。
5. 在 `main()` 初始化阶段调用 `efw_init()`，然后注册平台 HAL 和业务模块。

如果裁剪某个功能，需要在 Keil 的 `C/C++ > Define` 中同步关闭对应宏，例如 `EFW_ENABLE_COMM=0`。使用 `src/efw_all.c` 时，关闭的模块不会被包含进编译单元。

## 代码生成器第一阶段
可视化蓝图系统的第一步已经落到 CLI：`tools/efw_codegen.py` 可读取图描述 JSON，并生成可复制到真实项目的 `application/` 目录。当前 MVP 支持 GPIO 循迹输入、循迹传感器、PID、左右电机和 1ms LineFollower 控制流。

```bash
python3 tools/efw_codegen.py examples/graphs/line_tracking_car.json \
  -o application/generated_line_tracking_car \
  --force
```

生成代码仍然只依赖 EFW 的 application runtime 和 bind/update 句柄模式；真实项目中主要修改生成的 `app_platform.c`，把 mock 读写替换为 STM32 HAL、ESP-IDF、MSPM0 DriverLib 或自有 BSP 调用。更多说明见 `docs/codegen.md`。

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
#define EFW_ENABLE_ALGO_LOW_PASS 1
#define EFW_ENABLE_ALGO_RAMP 1
#define EFW_ENABLE_ALGO_ENCODER_SPEED 1
#define EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY 1
#define EFW_ENABLE_STATE_MACHINE 1
#define EFW_ENABLE_EVENT 1
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
  app_manifest.h       应用清单：启用功能、pool 容量、注册名称、控制策略
  app_bootstrap.c      应用 glue code：连接通用 runtime、pool、注册和 handle bind
  app_platform.c        底层适配回调、HAL/SENSOR/ACTUATOR 注册
  app_components.c      算法和可复用组件注册
  main.c                启动入口
```

真实项目迁移时，先在 `app_board_config.h` 设置引脚、PWM 通道、速度范围等参数，再在 `app_manifest.h` 设置启用功能、pool 容量和注册名称，最后在 `app_platform.c` 中把 mock 读写替换成 STM32 HAL、ESP-IDF 或 MSPM0 DriverLib 调用。

应用入口推荐保持极简：

```c
app_init();

while (1) {
    app_loop_1ms();
}
```

`include/efw/app/runtime.h` 和 `src/app/runtime.c` 提供通用 runtime；具体应用的 `app_bootstrap.c` 根据 `app_manifest.h` 自动完成 registry pool 初始化、平台注册、组件注册和 handle bind。用户不需要在 `main.c` 手动声明 pool 或 `efw_line_follower_t`。

## 竞赛推荐用法
高频控制路径推荐使用 `bind + update` 句柄模式：初始化时按名称查找一次，控制循环中只走缓存指针。

```c
efw_line_follower_config_t cfg = {
    .sensor_name = "line_sensor_5ch",
    .pid_name = "line_pid",
    .left_motor = "left_motor",
    .right_motor = "right_motor",
    .weights = weights,
    .base_speed = 65.0f,
    .min_speed = 0.0f,
    .max_speed = 100.0f,
    .dt = 0.001f,
    .active_value = 1,
    .binary_mode = 1,
};
efw_line_follower_bind_config(&follower, &cfg);
efw_line_follower_update(&follower, 0, 0);
```

`efw_sensor_read("name")`、`efw_algo_run("name")`、`efw_motor_set_diff("left", "right", ...)` 这类字符串 API 保留为低频/简单场景便捷入口；正式竞赛控制环优先使用 handle。

应用可以提供注册表 pool，减少默认静态数组浪费。推荐放在 `app_bootstrap.c`，由 `app_manifest.h` 的容量宏统一控制：

```c
static const efw_hal_ops_t *hal_pool[APP_HAL_COUNT];
efw_hal_registry_init_pool(hal_pool, APP_HAL_COUNT);
```

调试时可读取最近错误上下文：

```c
const efw_error_t *err = efw_diag_last_error();
```

低频事件可使用轻量 topic：

```c
efw_topic_subscribe(1, cb, user);
efw_topic_publish(1, &data, sizeof(data));
```

当前内置竞赛算法包括 PID、滑动均值、低通滤波、斜坡限速、编码器测速和互补滤波姿态解算。

简单验证或低频脚本可以使用字符串便捷 API：

```c
efw_line_tracking_follow_diff("line_sensor_5ch", "line_pid", "left_motor", "right_motor", weights, 45.0f, 0.001f, 0, 0);
```

正式控制循环不推荐每周期使用上面的字符串 API，推荐通过 `app_bootstrap.c` 自动 bind 后调用 `app_loop_1ms()`。
