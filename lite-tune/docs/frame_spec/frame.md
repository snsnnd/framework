# LiteTune v0.5.0 Frame Layer Specification

本文件定义 LiteTune 帧层，包括 WireFrame、RawFrame、COBS、CRC、FrameID 和基础收发流程。

相关文档：

- [公共约定](common.md)
- [Type 总表](common.md#type-table)
- [运行辅助：STATUS](runtime.md#status)
- [可靠性](reliability.md)

---

## 1. WireFrame

LiteTune 在线路上传输的是 `WireFrame`：

```text
WireFrame = COBS(RawFrame) + 0x00
```

结构图：

```text
WireFrame

+--------------------------------------+-------------+
| COBS encoded RawFrame                | Delimiter   |
| variable bytes                       | 0x00        |
+--------------------------------------+-------------+
```

规则：

```text
COBS encoded RawFrame 中不应包含 0x00。
0x00 只作为帧结束符。
连续多个 0x00 视为空帧，接收端应忽略。
```

---

## 2. RawFrame

RawFrame 是 COBS 编码前的数据结构。

```text
RawFrame

byte offset
0          2      3                         11
+----------+----------+----------------+------------------+----------+
| Magic    | Type     | FrameID        | Payload          | CRC16    |
| u16 LE   | u8       | u64 LE         | N bytes          | u16 LE   |
+----------+----------+----------------+------------------+----------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u16` | `Magic` | 固定 `0xA55A`，见 [Magic](common.md#magic) |
| 2 | `u8` | `Type` | 帧类型，见 [Type 总表](common.md#type-table) |
| 3 | `u64` | `FrameID` | 发送方生成的不透明帧 ID |
| 11 | `N bytes` | `Payload` | 由 Type 决定 |
| 11 + N | `u16` | `CRC16` | 对 `Magic..Payload` 计算 |

最小 RawFrame 长度：

```text
2 + 1 + 8 + 0 + 2 = 13 bytes
```

Payload 长度：

```text
payload_len = raw_frame_len - 13
```

LiteTune 不在 header 中单独放 `payload_len`。

---

## 3. RawFrame 字段

### 3.1 Magic

```text
Magic = 0xA55A
```

little-endian 字节序：

```text
5A A5
```

Magic 错误的帧必须丢弃。

### 3.2 Type

`Type` 决定 Payload 结构。完整 Type 表见 [common.md#type-table](common.md#type-table)。

### 3.3 FrameID

`FrameID` 是发送方生成的 `u64` 不透明帧 ID。

规则：

```text
1. FrameID 类型为 u64 little-endian。
2. RawFrame.FrameID 不应为 0。
3. Host 和 MCU 的 FrameID 空间相互独立。
4. 接收方不得根据 FrameID 数值推断时间、顺序或延迟。
5. 接收方只用 FrameID 做请求-响应匹配。
6. 响应帧 payload 中的 request_frame_id 必须等于原请求 FrameID。
7. request_frame_id = 0 表示无对应请求。
8. 同一连接 / 当前注册周期内，不同逻辑请求不应复用相同 FrameID。
```

FrameID 可以来自自增序号、高精度计数器、随机数或用户自定义编码。协议不解析其内部结构。

### 3.4 Payload

Payload 由 Type 决定。

模块文档：

- [DISCOVER / REGISTER_*](init.md)
- [LOG_REPORT](telemetry.md#log_report)
- [PARAM_SET / PARAM_GET / PARAM_REPORT](params.md)
- [CMD](cmd.md)
- [STATUS / LOG_TEXT](runtime.md)

### 3.5 CRC16

CRC16 详见 [CRC-16](#crc16)。

---

## 4. COBS 编码

发送端：

```text
1. 构造 RawFrame，不含 CRC16。
2. 计算 CRC16 并追加到 RawFrame 尾部。
3. 对完整 RawFrame 做 COBS 编码。
4. 发送 COBS 编码结果。
5. 发送 0x00 delimiter。
```

接收端：

```text
1. 持续接收字节。
2. 遇到 0x00，认为前面 bytes 是一个 COBS encoded frame。
3. 如果 encoded frame 长度为 0，忽略。
4. COBS 解码。
5. 得到 RawFrame。
6. 进入 RawFrame 校验流程。
```

COBS 缓冲区建议：

```c
encoded_max = raw_max + raw_max / 254 + 2;
```

其中 `+2` 用于 COBS overhead 和最终 delimiter。

---

## 5. CRC-16

推荐算法：

```text
CRC-16/MCRF4XX
```

参数：

```text
width  = 16
poly   = 0x1021
init   = 0xFFFF
refin  = true
refout = true
xorout = 0x0000
check("123456789") = 0x6F91
```

CRC 覆盖范围：

```text
Magic
Type
FrameID
Payload
```

CRC 不覆盖：

```text
CRC16 字段自身
COBS 编码结果
最后的 0x00 delimiter
```

CRC 在线路中按 little-endian 发送：

```text
low byte first
high byte second
```

---

## 6. 发送流程

```text
+-------------------+
| Build Payload     |
+---------+---------+
          |
          v
+-------------------+
| Build Header      |
| Magic Type        |
| FrameID           |
+---------+---------+
          |
          v
+-------------------+
| Append Payload    |
+---------+---------+
          |
          v
+-------------------+
| Calc CRC16        |
+---------+---------+
          |
          v
+-------------------+
| Append CRC16      |
+---------+---------+
          |
          v
+-------------------+
| COBS Encode       |
+---------+---------+
          |
          v
+-------------------+
| Send + 0x00       |
+-------------------+
```

伪代码：

```c
bool lt_send(uint8_t type, const uint8_t *payload, uint16_t payload_len) {
    uint8_t raw[LT_RAW_FRAME_SIZE];
    uint16_t n = 0;
    uint64_t frame_id = 0;

    if (lt_next_frame_id(&frame_id) != LT_STATUS_OK) return false;

    write_u16_le(raw, &n, 0xA55A);
    write_u8(raw, &n, type);
    write_u64_le(raw, &n, frame_id);
    write_bytes(raw, &n, payload, payload_len);

    uint16_t crc = crc16_mcrf4xx(raw, n);
    write_u16_le(raw, &n, crc);

    uint16_t enc_len = cobs_encode(raw, n, tx_encoded);
    tx_encoded[enc_len++] = 0x00;

    return transport_write(tx_encoded, enc_len);
}
```

---

## 7. 接收流程

```text
+-------------------+
| Receive Bytes     |
+---------+---------+
          |
          v
+-------------------+
| Wait 0x00         |
+---------+---------+
          |
          v
+-------------------+
| COBS Decode       |
+---------+---------+
          |
          v
+-------------------+
| Check Length      |
+---------+---------+
          |
          v
+-------------------+
| Check Magic       |
+---------+---------+
          |
          v
+-------------------+
| Check CRC16       |
+---------+---------+
          |
          v
+-------------------+
| Parse Header      |
+---------+---------+
          |
          v
+-------------------+
| Check FrameID     |
+---------+---------+
          |
          v
+-------------------+
| Dispatch Type     |
+-------------------+
```

伪代码：

```c
void lt_on_frame_delimited(const uint8_t *encoded, uint16_t encoded_len) {
    if (encoded_len == 0) return;

    uint8_t raw[LT_RAW_FRAME_SIZE];
    int raw_len = cobs_decode(encoded, encoded_len, raw);
    if (raw_len < 13) {
        counters.rx_decode_error_count++;
        maybe_send_status(LT_STATUS_FRAME_DECODE_ERROR);
        return;
    }

    if (read_u16_le(raw + 0) != 0xA55A) {
        counters.rx_decode_error_count++;
        maybe_send_status(LT_STATUS_FRAME_DECODE_ERROR);
        return;
    }

    uint16_t rx_crc = read_u16_le(raw + raw_len - 2);
    uint16_t calc = crc16_mcrf4xx(raw, raw_len - 2);
    if (rx_crc != calc) {
        counters.rx_crc_error_count++;
        maybe_send_status(LT_STATUS_CRC_ERROR);
        return;
    }

    uint8_t type = raw[2];
    uint64_t frame_id = read_u64_le(raw + 3);
    if (frame_id == 0) {
        counters.rx_bad_payload_count++;
        maybe_send_status(LT_STATUS_BAD_PAYLOAD);
        return;
    }

    const uint8_t *payload = raw + 11;
    uint16_t payload_len = raw_len - 13;

    lt_dispatch(type, frame_id, payload, payload_len);
}
```

---

## 8. 基础错误处理

以下错误应丢弃当前帧：

```text
COBS 解码失败
RawFrame 长度小于 13
Magic 错误
CRC 错误
FrameID 为 0
未知 Type
Payload 格式错误
```

MCU 可以使用 [STATUS](runtime.md#status) 上报协议层错误：

| 错误 | 建议 STATUS |
|---|---|
| COBS 解码失败 | `FRAME_DECODE_ERROR` |
| RawFrame 长度小于 13 | `FRAME_DECODE_ERROR` |
| Magic 错误 | `FRAME_DECODE_ERROR` |
| CRC 错误 | `CRC_ERROR` |
| FrameID 为 0 | `BAD_PAYLOAD` |
| 未知 Type | `UNKNOWN_TYPE` |
| Payload 格式错误 | `BAD_PAYLOAD` |

`STATUS` 是异步通知，不完成任何 pending request。业务请求的错误结果按各模块规则返回：

| 请求 | 错误响应 |
|---|---|
| [PARAM_SET](params.md#param_set) | [PARAM_REPORT](params.md#param_report) |
| [PARAM_GET](params.md#param_get) | [PARAM_REPORT](params.md#param_report) |
| [CMD_REQUEST](cmd.md#cmd_request) | [CMD_RESPONSE](cmd.md#cmd_response) |

---

## 9. 最大帧长度

协商后最大 RawFrame：

```text
peer_max_decoded_frame = min(host_max_decoded_frame, mcu_max_decoded_frame)
```

发送方必须保证：

```text
raw_frame_len <= peer_max_decoded_frame
```

单帧规则：

```text
一个 RawFrame 必须携带一个完整逻辑消息。
发送方不得依赖连续帧重组来传输一个逻辑消息。
如果完整逻辑消息无法放入 peer_max_decoded_frame，应返回 TOO_LARGE、发送 STATUS、丢弃该事件，或在本地注册阶段失败。
```

`host_max_decoded_frame` 定义在 [DISCOVER](init.md#discover)。
`mcu_max_decoded_frame` 定义在 [REGISTER_BEGIN](init.md#register_begin)。
