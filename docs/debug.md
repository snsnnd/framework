# EFW 在线调试功能使用说明

## 概述

EFW 在线调试功能通过 LiteTune 协议实现 MCU 数据的实时采集、比对分析、记录回放。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host (PC)                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ efw.py live  │───▶│ LiteTune     │───▶│  PyQt Debug  │      │
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
│  │  注册表数据  │    │   模块       │    │  监控点      │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 列出可用串口

```bash
python3 tools/efw.py live ports
```

### 2. 读取单次快照

```bash
python3 tools/efw.py live snapshot --port /dev/ttyUSB0 --pretty
```

### 3. 持续记录数据

```bash
python3 tools/efw.py live record --port /dev/ttyUSB0 -o debug.jsonl --interval 100
```

### 4. 带比对的记录

```bash
python3 tools/efw.py live record --port /dev/ttyUSB0 -o debug.jsonl \
    --expected examples/debug/line_tracker_expected.json
```

### 5. 分析记录文件

```bash
# 查看摘要
python3 tools/efw.py live analyze debug.jsonl --action summary

# 查看所有问题
python3 tools/efw.py live analyze debug.jsonl --action issues

# 参数统计
python3 tools/efw.py live analyze debug.jsonl --action stats --param motor_speed

# 导出为 CSV
python3 tools/efw.py live analyze debug.jsonl --action export -o debug.csv
```

### 6. 启动 PyQt 调试面板

```bash
python3 tools/efw.py live panel --port /dev/ttyUSB0
```

## MCU 端集成

### 1. 包含头文件

```c
#include "efw/debug/efw_debug.h"
```

### 2. 初始化调试模块

```c
void app_init(void) {
    // 初始化 EFW 框架
    efw_init();
    
    // 注册 HAL、传感器、算法等
    // ...
    
    // 初始化调试模块
    efw_debug_init();
    
    // 注册 EFW 框架数据
    efw_debug_register_all_efw();
    
    // 注册自定义监控点
    efw_debug_register_custom("motor_pwm", EFW_DEBUG_TYPE_U16, &motor_pwm_value);
}
```

### 3. 在主循环中更新

```c
void app_loop_1ms(void) {
    // 业务逻辑
    // ...
    
    // 更新调试数据（建议每 10-100ms 调用一次）
    static uint16_t debug_counter = 0;
    if (++debug_counter >= 10) {  // 每 10ms
        debug_counter = 0;
        efw_debug_update();
    }
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
│   └── efw_debug.h              # MCU 端调试模块头文件
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
    └── line_tracker_expected.json  # 示例预期配置
```

## 编译配置

在 CMakeLists.txt 中可以通过以下选项控制调试模块：

```cmake
option(EFW_ENABLE_DEBUG "Enable online debug module" ON)
```

或在编译时禁用：

```bash
cmake -S . -B build -DEFW_ENABLE_DEBUG=OFF
```
