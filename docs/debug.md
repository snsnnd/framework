# EFW 在线调试功能使用说明

## 概述

EFW 在线调试通过 LiteTune 协议把 MCU 侧监控点注册为 Host 可发现、可读取的参数，并提供 EFW 专用命令读取统计和快照。当前闭环包括：MCU 监控点表、LiteTune 参数注册、COBS/CRC 串口收发、Host schema discovery、`param get --all` 快照读取和 `debug.stats` 命令。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host (PC)                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ efw.py debug │───▶│ LiteTune     │───▶│  PyQt Debug  │      │
│  │    CLI       │    │   Daemon     │    │    Panel     │      │
│  └──────────────┘    └──────┬───────┘    └──────────────┘      │
│                             │ UDS                               │
│                             ▼                                   │
│                     ┌──────────────┐                            │
│                     │  lt.py CLI   │                            │
│                     └──────┬───────┘                            │
└────────────────────────────┼────────────────────────────────────┘
                             │ Serial (COBS/CRC)
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                         MCU                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  EFW 框架    │───▶│ efw_debug    │◀───│ 用户自定义   │     │
│  │  注册表数据  │    │  监控点表     │    │  监控点      │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 列出可用串口

```bash
python3 tools/debug/cli.py ports
```

### 2. 读取单次快照

```bash
python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
```

### 3. 持续记录数据

```bash
python3 tools/efw.py debug record --port /dev/ttyUSB0 -o debug.jsonl --duration 60
```

### 4. 带比对的记录

```bash
python3 tools/debug/cli.py record --port /dev/ttyUSB0 -o debug.jsonl \
    --expected examples/debug/line_tracker_expected.json
```

### 5. 分析记录文件

```bash
# 查看摘要
python3 tools/debug/cli.py analyze debug.jsonl --action summary

# 查看所有问题
python3 tools/debug/cli.py analyze debug.jsonl --action issues

# 参数统计
python3 tools/debug/cli.py analyze debug.jsonl --action stats --param motor_speed

# 导出为 CSV
python3 tools/debug/cli.py analyze debug.jsonl --action export -o debug.csv
```

### 6. 启动 PyQt 调试面板

```bash
python3 tools/debug/cli.py panel --port /dev/ttyUSB0
```

## MCU 端集成

### 1. 包含头文件

```c
#include "efw/debug/efw_debug.h"
#include "efw/debug/efw_debug_litetune.h"
```

推荐用工具生成单文件传输适配层：

```bash
python3 tools/efw.py debug transport-template litetune --transport uart -o board_adapters/efw_litetune_transport_port.c
```

这里的 `litetune` 是调试通信协议栈，`--transport uart` 是承载方式。也可以用 `--transport usb-cdc` 生成同一协议的 USB CDC 接入模板。用户只需要修改生成文件里的 `app_debug_transport_write_bytes()`，把字节写到 UART 或 USB CDC。LiteTune 协议帧、COBS、CRC、schema、param 和 command 都由 EFW/LiteTune 内部处理，不需要用户手写通信协议。

应用代码只需要声明并调用这三个 transport 函数：

```c
efw_status_t app_debug_transport_start(const char *device_name, uint16_t telemetry_period_ms);
void app_debug_transport_on_rx(const uint8_t *data, uint16_t len);
void app_debug_transport_poll_1ms(uint16_t telemetry_period_ms);
```

### 2. 初始化调试模块

```c
void app_init(void) {
    // 初始化 EFW 框架
    efw_init();
    
    // 注册 HAL、传感器、算法等
    // ...
    
    // 初始化调试模块。
    efw_debug_init();
    
    // 注册 EFW 框架数据
    efw_debug_register_all_efw();
    
    // 注册自定义监控点
    efw_debug_register_custom("motor_pwm", EFW_DEBUG_TYPE_U16, &motor_pwm_value);

    // 使用单文件 transport port 初始化 LiteTune。
    app_debug_transport_start("efw-board", 100);
}
```

### 3. 在主循环中更新

```c
void app_loop_1ms(void) {
    // 业务逻辑
    // ...
    
    // 更新调试统计并检查监控点有效性（建议每 10-100ms 调用一次）
    static uint16_t debug_counter = 0;
    if (++debug_counter >= 10) {  // 每 10ms
        debug_counter = 0;
        // 如果使用 app_debug_transport_poll_1ms()，这里不需要手动 report。
    }

    // 必须高频调用，用于处理 LiteTune RX ring、TX queue 和周期 telemetry。
    app_debug_transport_poll_1ms(100);
}
```

串口接收中断或 DMA 回调中把收到的字节喂给 LiteTune：

```c
void USARTx_RxCallback(const uint8_t *data, uint16_t len) {
    app_debug_transport_on_rx(data, len);
}
```

### 4. 批量注册自定义监控点

```c
void register_custom_debug_points(void) {
    efw_debug_point_t points[] = {
        {"motor_left_speed", EFW_DEBUG_SOURCE_CUSTOM, EFW_DEBUG_TYPE_F32, &left_speed, 0, 0},
        {"motor_right_speed", EFW_DEBUG_SOURCE_CUSTOM, EFW_DEBUG_TYPE_F32, &right_speed, 0, 0},
        {"battery_voltage", EFW_DEBUG_SOURCE_CUSTOM, EFW_DEBUG_TYPE_F32, &battery_v, 0, 0},
    };
    efw_debug_register_custom_batch(points, 3);
}
```

## 预期配置文件格式

```json
{
    "version": "1.0",
    "params": {
        "param_name": {
            "min": 0,
            "max": 100,
            "exact": 42,
            "enum": [0, 1, 2],
            "type": "f32",
            "unit": "%",
            "required": true,
            "description": "参数描述"
        }
    }
}
```

## JSONL 日志格式

```jsonl
{"type":"session_start","session_id":"20260701_120000","time":"2026-07-01T12:00:00Z"}
{"type":"snapshot","seq":1,"record_time":"2026-07-01T12:00:01Z","params":{"motor_speed":{"value":50,"type":"f32","unit":"%"}}}
{"type":"issue","seq":2,"record_time":"2026-07-01T12:00:02Z","name":"motor_speed","type":"out_of_range","detail":"120 > max(100)"}
{"type":"session_end","session_id":"20260701_120000","record_count":100,"elapsed_seconds":10.5}
```

## 文件结构

```
framework/
├── include/efw/debug/
│   ├── efw_debug.h              # MCU 端调试模块头文件
│   └── efw_debug_litetune.h     # LiteTune 集成 API
│
├── src/debug/
│   ├── efw_debug.c              # MCU 端核心实现
│   └── efw_debug_litetune.c    # LiteTune 集成层
│
├── tools/debug/
│   ├── __init__.py
│   ├── cli.py                   # CLI 入口
│   ├── collector.py             # 数据采集器
│   ├── comparator.py            # 比对引擎
│   ├── recorder.py              # 数据记录器
│   ├── analyzer.py              # 历史分析
│   └── panel.py                 # PyQt 面板
│
└── examples/debug/
    ├── efw_litetune_transport_port.c # 单文件 UART/USB CDC 传输适配模板
    └── line_tracker_expected.json    # 示例预期配置
```

## 编译配置

在 CMakeLists.txt 中可以通过以下选项控制调试模块。默认关闭，避免主机验证
或裸机轻量集成时默认拉入调试/LiteTune 相关源码：

```cmake
option(EFW_ENABLE_DEBUG "Enable online debug module" OFF)
option(EFW_ENABLE_LITETUNE "Enable LiteTune backend for online debug" OFF)
```

编译时启用：

```bash
cmake -S . -B build -DEFW_ENABLE_DEBUG=ON -DEFW_ENABLE_LITETUNE=ON
```

## 当前边界

- 已支持：自定义监控点注册、HAL/传感器/算法枚举注册、LiteTune 参数表注册、LiteTune 命令注册、`param get --all`、`debug.stats`、`debug.list`、`debug.snapshot`、可选 packed telemetry。
- Host 工具主路径：`tools/debug/collector.py` 通过 LiteTune daemon 读取 schema 和参数；`tools/debug/cli.py stats` 通过 LiteTune command path 读取 EFW debug 统计。
- LiteTune discovery 使用静态 registry；需要先完成 `efw_debug_register_*()`，再调用 `efw_debug_litetune_init()`。运行中新增监控点需要重新初始化/重新 discovery 才能被 Host schema 发现。
- 状态机当前状态属于动态字符串值，当前没有自动注册为 LiteTune string 参数；LiteTune string 需要 `lt_str8_view_t` 存储形态，EFW 暂时只自动注册数值/bool 监控点。
