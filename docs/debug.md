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
│                             │ Local IPC                         │
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

同步发送 transport 在 `send` 成功返回后由 EFW 自动完成本批发送。异步 UART/DMA transport 必须设置 `.send_mode = EFW_DEBUG_LITETUNE_SEND_ASYNC`，并在且仅在成功发送对应的完成回调中调用 `efw_debug_litetune_tx_complete()`。ISR 与主循环并发使用 LiteTune 时，平台还必须成对定义 `LT_CRITICAL_ENTER/EXIT`，并恢复进入前的中断状态。

启用 runtime trace 后，Scheduler 会输出 `scheduler.task.begin/end`，end 事件包含 `lateness_ms`、`runtime_us`、`missed` 和 `overruns`。若需要真实 WCET 数据，必须在注册任务前通过 `efw_scheduler_set_time_providers()` 提供平台微秒时钟；Graph 的逻辑 tick 只能作为 release 时间，不能替代高精度执行计时。

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
│   ├── efw_debug_litetune.h     # LiteTune 集成 API
│   └── litetune/                # EFW 内置 LiteTune MCU 通信层副本
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

## EFW Ground Station 与协议 Profile

LiteTune 在 EFW 中被定位为地面站通信基础，而不是 PID 专用工具。PC 端入口位于
`tools/groundstation/`，负责串口 daemon、schema discovery、参数读写、命令调用、
日志/遥测记录。

生成可编辑协议 profile：

```bash
python3 tools/efw.py debug protocol init efw_protocol_profile.json
```

查看当前 profile：

```bash
python3 tools/efw.py debug protocol show efw_protocol_profile.json
```

项目可以在 `.efw_project.json` 中配置：

```json
{
  "protocol_profile": "efw_protocol_profile.json"
}
```

profile 可覆盖：

- `features`: Host 请求的功能位映射。
- `frame_types`: 标准帧 ID 映射。
- `extensions.frame_types`: 项目私有帧。
- `value_types` / `extensions.value_types`: 参数和日志字段类型。
- `project_frame_range`: 项目私有帧 ID 范围。
- `project_status_range` / `extensions.status_names`: 项目私有状态码。

MCU 端 trace 事件保持低耦合：`app/runtime` 和 `state_machine` 只暴露 callback，不依赖
LiteTune。启用 `EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE` 后，`efw_debug_litetune_init()`
会自动把 runtime/state-machine trace 接到 LiteTune packed log layout `0x11`。该 layout
包含 `trace.event_id`、`trace.name_id`、`trace.status`、`trace.mcu_time_ms`、`trace.duration_ms`，
其中 event/name 使用稳定 dictionary hash ID，避免实时路径传大段文本。若 Host 不支持 packed log，
bridge 会回退到 `LOG_TEXT`：

- `app.init.begin` / `app.init.end`
- `app.step.begin` / `app.step.end`
- `app.update.begin` / `app.update.end`
- `sm.transition`

trace 文本包含 MCU 侧 timing 字段：

- `mcu_time_ms`: MCU/runtime 时间源给出的毫秒时间戳。
- `duration_ms`: begin/end 成对事件的持续时间；无法计算时为 `unknown`。
- `time_in_state_ms`: 状态机 transition 前在旧状态停留的时间。

为避免调试回传破坏实时任务，EFW/LiteTune trace 默认采用有界队列和预算 flush：

- 正常任务上下文只把 trace record 复制进本地 ring buffer，不执行 COBS/CRC/串口发送。
- `efw_debug_litetune_process()` 默认每次最多 flush 少量 trace 事件。
- 空闲循环可以调用 `efw_debug_litetune_process_budget(max_trace_events)` 增加预算。
- Host 尚未连接时不会弹出 trace queue，避免初始化阶段日志被丢掉。
- 队列满时丢弃新 trace 并计入 `events_dropped`，不阻塞控制任务。
- 崩溃/错误路径可调用 `efw_debug_litetune_panic_flush(max_trace_events)` 做 best-effort flush。
- Host 可通过 `debug.perf` 查看 `events_received/events_queued/events_flushed/events_dropped/current_queue_depth/max_queue_depth/process_calls`。

推荐主循环结构：

```c
for (;;) {
    app_loop_tick();                 /* 正常实时任务 */
    efw_debug_litetune_process_budget(2u); /* idle/debug 预算 */
}
```

后续 Graph 生成代码可以在节点执行和数据搬运处调用 `efw_app_trace_event(...)`，实现
节点生命周期和数据流 trace，而不需要直接依赖 LiteTune。

```cmake
option(EFW_ENABLE_DEBUG "Enable online debug module" OFF)
option(EFW_ENABLE_LITETUNE "Enable LiteTune backend for online debug" OFF)
```

编译时启用：

```bash
cmake -S . -B build -DEFW_ENABLE_DEBUG=ON -DEFW_ENABLE_LITETUNE=ON
```

## 当前边界

- 已支持：自定义监控点注册、HAL/传感器/算法枚举注册、LiteTune 参数表注册、LiteTune string 参数 wrapper、LiteTune 命令注册、`param get --all`、`debug.stats`、`debug.list`、`debug.snapshot`、packed telemetry、packed trace。
- Host 工具主路径：`tools/debug/collector.py` 通过 LiteTune daemon 读取 schema 和参数；`tools/debug/cli.py stats` 通过 LiteTune command path 读取 EFW debug 统计。
- LiteTune discovery 使用静态 registry；需要先完成 `efw_debug_register_*()`，再调用 `efw_debug_litetune_init()`。运行中新增监控点需要重新初始化/重新 discovery 才能被 Host schema 发现。
- `EFW_DEBUG_TYPE_STRING` 会映射为 LiteTune `LT_VALUE_STRING`，bridge 内部维护稳定 `lt_str8_view_t` wrapper，并在 process/report 前刷新长度和指针；用户仍需保证原始字符串缓冲区在监控点生命周期内有效。
