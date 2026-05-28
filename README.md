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
- `src/`：库源码，按 `core/hal/algorithm` 分层，可加入 Keil、STM32CubeIDE、ESP-IDF 或 CMake 工程
- `examples/`：裸机风格示例
- `docs/`：设计说明

## 快速接入
1. 把 `include/` 加入头文件路径。
2. 把 `src/**/*.c` 加入工程编译。
3. 在系统启动后调用 `efw_init()`。
4. 注册 BSP HAL、通信对象、传感器、算法和模块。
5. 在主循环或定时任务里调用 `efw_sensor_read()`、`efw_algo_run()`、`efw_module_poll_all()` 等接口。

## Keil 接入
Keil 不需要 CMake，直接以源码库方式接入：

1. 在 `Options for Target > C/C++ > Include Paths` 添加 `framework/include`。
2. 新建一个 `EFW` Group。
3. 把以下文件加入 Group：
```text
src/algorithm/algorithms.c
src/core/registry.c
src/hal/hal_comm_registry.c
```
4. 应用代码包含 `#include "efw/efw.h"`。
5. 在 `main()` 初始化阶段调用 `efw_init()`，然后注册平台 HAL 和业务模块。

## CMake 构建
CMake 只用于主机侧编译验证或支持 CMake 的工程，不是裸机接入必需项。

```bash
cmake -S . -B build -DEFW_BUILD_EXAMPLES=ON
cmake --build build
```

## 配置
默认容量在 `include/efw/core/config.h` 中定义，可在编译参数里覆盖：

```c
#define EFW_MAX_HALS 16
#define EFW_MAX_COMMS 16
#define EFW_MAX_MODULES 32
#define EFW_MAX_SENSORS 32
#define EFW_MAX_ALGOS 16
#define EFW_MAX_STATE_MACHINES 8
```

## 当前能力
- HAL 注册、查找和便捷读写
- COMM 注册、HAL 绑定和便捷收发
- MODULE 注册、单个/全部初始化启动轮询
- SENSOR 注册、HAL/COMM 绑定和便捷读取
- ALGORITHM 注册和运行
- 内置 PID 与滑动均值算法
- STATE MACHINE 注册和查找
