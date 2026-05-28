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
4. 注册 SENSOR，例如 `line_adc` 绑定 `adc1`。
5. 注册 ALGORITHM，例如 `motor_pid`。
6. 注册 MODULE，并在主循环中轮询。

## 4. 绑定规则
- `efw_comm_ops_t.hal_name` 指向一个已注册 HAL。
- `efw_sensor_ops_t.hal_name` 指向一个已注册 HAL。
- `efw_sensor_ops_t.comm_name` 指向一个已注册 COMM。
- 注册时会检查绑定目标是否存在，避免运行后才暴露配置错误。

## 5. 传感器注册表
- 统一接口：`init/read`。
- 关键字段：`name/type/channel_count/hal_name/comm_name`。
- 示例：4 路循迹和 8 路循迹都使用 `EFW_SENSOR_LINE_TRACKING`，通过 `channel_count` 区分。

## 6. 算法注册表
- 算法通过 `efw_algo_ops_t` 挂载。
- 当前内置 `efw_pid_run()` 和 `efw_moving_avg_run()`。
- 应用层通过 `efw_algo_run("motor_pid", &input, &output)` 调用。

## 7. 模块注册表
- 模块用于管理驱动、服务和应用逻辑生命周期。
- 支持 `init/start/stop/poll`。
- 主循环可直接调用 `efw_module_poll_all()`。

## 8. 平台迁移建议
- STM32：HAL 回调中调用 STM32 HAL/LL，例如 `HAL_UART_Transmit`、`HAL_ADC_GetValue`。
- ESP32：HAL 回调中调用 ESP-IDF driver，例如 `uart_write_bytes`、`i2c_master_transmit`。
- MSPM0：HAL 回调中调用 DriverLib，例如 `DL_UART_transmitDataBlocking`。
- 对上层应用来说，平台差异只体现在注册的 HAL 回调实现。

## 9. Keil 工程接入
- Keil 不使用 CMake 时，直接把 `include` 加入 Include Paths。
- 把 `src/algorithm/algorithms.c`、`src/core/registry.c`、`src/hal/hal_comm_registry.c` 加入工程 Group。
- 如果后续新增源码文件，只需要继续加入对应 `.c` 文件。
- 用户自己的 STM32 HAL、LL 或寄存器代码只写在 BSP 回调里，不需要修改 EFW 源码。
