# LiteTune v0.5.0 Telemetry Specification

本文件定义遥测模块。核心帧 Type：

```text
LOG_REPORT
```

遥测字段的结构由初始化阶段的 [REGISTER_LOG_LAYOUT](init.md#register_log_layout) 注册。Host 必须先完成 [REGISTER](init.md#register) 后才能正确解析 LOG_REPORT。

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [Value Type](common.md#value-type)
- [REGISTER_LOG_LAYOUT](init.md#register_log_layout)

---

## 1. 遥测流程

```text
REGISTER 阶段

MCU -> Host:
  REGISTER_LOG_LAYOUT
    layout_id
    field_id
    value_type
    name
    unit

运行阶段

MCU -> Host:
  LOG_REPORT
    layout_id
    sample_seq
    packed_values
```

---

## 2. LOG_REPORT

### 2.1 方向

```text
MCU -> Host
```

### 2.2 作用

上报实时遥测数据，例如：

```text
target_speed
current_speed
pid_error
motor_pwm
roll
pitch
yaw
gyro_x
battery_voltage
external_state
```

### 2.3 Type

```text
Type  = 0x11
```

低频、不固定字段、事件型状态可使用 [LOG_TEXT](runtime.md#log_text) 或项目私有扩展 Type。

### 2.4 LOG_REPORT RawFrame 结构图

```text
LOG_REPORT RawFrame

+----------+----------+----------------+--------------------+----------+
| Magic    | Type     | FrameID        | LOG_REPORT Payload | CRC16    |
| u16      | 0x11     | u64            | variable           | u16      |
+----------+----------+----------------+--------------------+----------+
```

规则：

```text
1. FrameID 由发送方生成。
2. layout_id 必须是已注册 layout。
3. LOG_REPORT 不要求 Host 回复。
```

---

## 3. Packed Single Sample

### 3.1 使用场景

适合高频、固定字段顺序的遥测，例如 PID 曲线。

### 3.2 Payload 结构图

```text
LOG_REPORT Packed Single Payload

offset
0             1             3
+-------------+-------------+---------------------------+
| layout_id   | sample_seq  | packed_values             |
| u8          | u16         | by REGISTER_LOG_LAYOUT    |
+-------------+-------------+---------------------------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `layout_id` | Layout ID |
| 1 | `u16` | `sample_seq` | 当前 layout 内样本序号 |
| 3 | variable | `packed_values` | 按 [REGISTER_LOG_LAYOUT](init.md#register_log_layout) 字段顺序排列 |

### 3.3 解析规则

Host 查找 `layout_id` 对应的 layout：

```text
field[0].value_type -> 解析 value 0
field[1].value_type -> 解析 value 1
field[2].value_type -> 解析 value 2
...
```

如果 payload 解析后还有剩余字节，Host 应认为该帧 `BAD_PAYLOAD`。

---

## 4. 错误处理

LOG_REPORT 不要求业务响应。Host 发现错误时通常只记录统计。

错误情况：

```text
layout_id 未注册
payload 长度与 layout 不匹配
value_type 不支持
```

Host 可在本地增加计数：

```text
telemetry_unknown_layout_count
telemetry_bad_payload_count
```

---

## 5. 最小实现

最小遥测实现只需要：

```text
REGISTER_LOG_LAYOUT
LOG_REPORT Packed Single Sample
```
