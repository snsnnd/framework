# EFW Ground Station / PID Scope

`tools/efw_ground_station.py` 是面向 EFW 的轻量地面站和数据可视化工具。它参考 PIDScope Offline 的思路，把 **串口接收、二进制协议、实时曲线、CSV 导出、基础阶跃指标、PARAM_SET 写参** 整合到当前框架中。

## 依赖安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r tools/requirements-ground-station.txt
```

依赖包含：

- `PyQt6`：桌面 UI。
- `pyqtgraph`：实时曲线。
- `pyserial`：串口通信。

如果暂时没有硬件，可以直接使用模拟数据：

```bash
python3 tools/efw_ground_station.py
```

打开后点击 **Start Simulation**，即可看到 target、feedback、error、output 曲线。

## 协议

协议实现分为两端：

- Python：`tools/efw_telemetry.py`
- C：`include/efw/debug/pid_scope.h` + `src/debug/pid_scope.c`

帧格式：

```text
SOF(0xAA 0x55) + msg_type:u8 + payload_len:u16-le + payload + crc16:u16-le
```

CRC16 使用 Modbus/IBM 多项式 `0xA001`，计算范围是 `msg_type + payload_len + payload`。

### TELEMETRY payload

`msg_type = 0x01`，字段为：

```text
device_id:u8
channel_id:u8
time_ms:u32-le
target:f32
feedback:f32
error:f32
output:f32
kp:f32
ki:f32
kd:f32
extra1:f32
extra2:f32
```

约定建议：

- `device_id`：机器人或控制板编号。
- `channel_id`：不同控制环编号，例如循迹、左轮速度、右轮速度、姿态角速度。
- `extra1`：建议放电池电压，便于后续做电压分段调参。
- `extra2`：保留给温度、模式号或其他现场调试量。

### PARAM_SET payload

`msg_type = 0x02`，字段为：

```text
device_id:u8
channel_id:u8
kp:f32
ki:f32
kd:f32
```

地面站点击 **Send PARAM_SET** 时会发送此帧。嵌入式端可以用 `efw_pid_scope_parse_param_set_frame()` 解析后更新对应 PID 参数。

## 嵌入式端发送示例

```c
#include "efw/efw.h"

static uint8_t tx_frame[EFW_PID_SCOPE_MAX_FRAME];

void app_debug_send_pid(float target, float feedback, float output) {
    efw_pid_scope_telemetry_t t = {
        .device_id = 1,
        .channel_id = 1,
        .time_ms = app_millis(),
        .target = target,
        .feedback = feedback,
        .error = target - feedback,
        .output = output,
        .kp = 18.0f,
        .ki = 0.0f,
        .kd = 2.5f,
        .extra1 = app_battery_voltage(),
        .extra2 = 0.0f,
    };
    uint16_t len = 0;
    if (efw_pid_scope_encode_telemetry(&t, tx_frame, sizeof(tx_frame), &len) == EFW_OK) {
        uart_write(tx_frame, len);
    }
}
```

## 当前项目仍然存在的问题

地面站补齐了“看数据、调参数”的闭环，但当前项目离完整竞赛工具链还有这些问题：

1. **图形编辑器仍是 MVP**：现在主要覆盖循迹小车拓扑；后续需要把 IMU、编码器、速度闭环、状态机和事件节点做成可配置卡片。
2. **调参协议只是基础版**：已有 TELEMETRY 和 PARAM_SET，但还没有参数持久化、参数版本号、权限保护、批量写参和设备扫描。
3. **生成器模板还偏硬编码**：line follower 生成链路可用，但多 flow、多周期任务、多模块组合仍需扩展。
4. **地面站没有和 visual editor 合并为一个壳**：当前是两个工具，下一步可以做成同一个 PyQt 主程序里的两个页面：Blueprint 和 Ground Station。
5. **自动分析还偏基础**：目前只有 overshoot、steady_error、IAE、oscillations；后续可加入增益调度建议、阶跃自动识别、离线日志回放和热力图。
