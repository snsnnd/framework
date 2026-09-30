# LiteTune v0.5.0 Runtime Frames Specification

本文件定义运行辅助帧：

```text
STATUS
LOG_TEXT
```

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [Status Code](common.md#status-code)
- [可靠性](reliability.md)

---

## 1. STATUS

### 1.1 方向

```text
MCU -> Host
```

### 1.2 作用

`STATUS` 是 MCU 到 Host 的轻量异步错误/状态通知。

```text
1. STATUS 不完成任何 pending request。
2. STATUS 不替代 PARAM_REPORT、CMD_RESPONSE 或 REGISTER_END。
3. STATUS 不携带 request_frame_id。
4. STATUS 不要求 Host 回复。
5. STATUS 按 best-effort 发送。
6. MCU 应对重复 STATUS 做限流。
```

### 1.3 Type

```text
Type  = 0x07
```

### 1.4 完整帧结构图

```text
STATUS RawFrame

+----------+----------+----------------+------------------+----------+
| Magic    | Type     | FrameID        | STATUS Payload   | CRC16    |
| u16      | 0x07     | u64            | 1 byte           | u16      |
+----------+----------+----------------+------------------+----------+
```

RawFrame 总长度：

```text
13 + 1 = 14 bytes
```

### 1.5 Payload 结构图

```text
STATUS Payload

+-------------+
| status_code |
| u8          |
+-------------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `status_code` | 见 [Status Code](common.md#status-code) |

### 1.6 使用场景

适合用 STATUS 上报：

```text
VERSION_UNSUPPORTED
UNKNOWN_TYPE
BAD_PAYLOAD
TOO_LARGE
BUSY
NOT_READY
INVALID_STATE
FRAME_DECODE_ERROR
CRC_ERROR
RX_OVERFLOW
TX_DROP
UNKNOWN_ERROR
```

业务请求失败时使用业务响应：

```text
PARAM_SET 失败 -> PARAM_REPORT
PARAM_GET 失败 -> PARAM_REPORT
CMD_REQUEST 失败 -> CMD_RESPONSE
```

---

## 2. LOG_TEXT

### 2.1 方向

```text
MCU -> Host
```

### 2.2 作用

发送文本日志。

高速数据应使用 [LOG_REPORT](telemetry.md#log_report)。

### 2.3 Type

```text
Type  = 0x12
```

### 2.4 完整帧结构图

```text
LOG_TEXT RawFrame

+----------+----------+----------------+------------------+----------+
| Magic    | Type     | FrameID        | LOG_TEXT Payload | CRC16    |
| u16      | 0x12     | u64            | variable         | u16      |
+----------+----------+----------------+------------------+----------+
```

### 2.5 Payload 结构图

```text
LOG_TEXT Payload

+------------+-----------+
| level      | text      |
| u8         | str8      |
+------------+-----------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `level` | 日志等级 |
| 1 | `str8` | `text` | UTF-8 文本 |

`level`：

| 值 | 名称 |
|---:|---|
| `0x00` | DEBUG |
| `0x01` | INFO |
| `0x02` | WARN |
| `0x03` | ERROR |
| `0x04` | FATAL |
| `0x05-0x7F` | reserved |
| `0x80-0xFF` | user-defined |

规则：

```text
1. text 使用 str8。
2. LOG_TEXT Payload 不包含 C string 结尾的 '\0'。
3. UTF-8 字节长度必须 <= 255。
4. 长日志应由发送方拆成多条 LOG_TEXT。
```
