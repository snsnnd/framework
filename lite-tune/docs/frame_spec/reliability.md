# LiteTune v0.5.0 Reliability Specification

本文件定义 LiteTune 的请求响应匹配、基础接收检查和帧长度限制。

协议层不定义自动重发机制。发送方若需要超时处理，应在自身业务层处理，不改变 LiteTune 帧语义。

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [STATUS](runtime.md#status)
- [PARAM_REPORT](params.md#param_report)
- [CMD_RESPONSE](cmd.md#cmd_response)

---

## 1. 请求响应关系

```text
DISCOVER      -> REGISTER_BEGIN ... REGISTER_END
PARAM_SET     -> PARAM_REPORT
PARAM_GET     -> PARAM_REPORT
CMD_REQUEST   -> CMD_RESPONSE
STATUS        -> 无响应
LOG_REPORT    -> 无响应
LOG_TEXT      -> 无响应
```

`STATUS` 是异步状态通知，不完成任何 pending request。

---

## 2. FrameID 匹配

FrameID 是请求-响应匹配的唯一协议字段。

规则：

1. 请求帧的 `RawFrame.FrameID` 不应为 0。
2. 响应帧 payload 中的 `request_frame_id` 必须等于原请求 `FrameID`。
3. `request_frame_id = 0` 表示无对应请求。
4. Host 和 MCU 的 FrameID 空间相互独立。
5. 接收方不得根据 FrameID 数值推断时间、顺序或延迟。

---

## 3. DISCOVER 匹配

```text
DISCOVER

+-----------------------------+
| DISCOVER                    |
| FrameID = F1                |
+--------------+--------------+
               |
               v
+-----------------------------+
| REGISTER_BEGIN              |
| Type = 0x02                 |
+--------------+--------------+
               |
               v
+-----------------------------+
| REGISTER records...         |
| Type = 0x03..0x05           |
+--------------+--------------+
               |
               v
+-----------------------------+
| REGISTER_END                |
| Type = 0x06                 |
+-----------------------------+
```

DISCOVER 对应的是完整 REGISTER_* 序列。REGISTER_* payload 不携带 `request_frame_id`，注册记录类型由 RawFrame.Type 区分。

Host 规则：

1. 发送新的 `DISCOVER` 时清空 pending request。
2. 收到 `REGISTER_BEGIN` 时清空 pending request 和已保存的注册信息。
3. 收到 `REGISTER_END` 后建立当前解析表。
4. 不跨 REGISTER 周期保留 pending request。

---

## 4. PARAM 匹配

```text
PARAM_SET / PARAM_GET

+-----------------------------+
| PARAM_SET or PARAM_GET      |
| FrameID = F2                |
+--------------+--------------+
               |
               v
+-----------------------------+
| PARAM_REPORT                |
| request_frame_id = F2       |
+-----------------------------+
```

匹配字段：

```text
PARAM_REPORT.request_frame_id = PARAM_SET.FrameID
PARAM_REPORT.request_frame_id = PARAM_GET.FrameID
```

相关帧：

- [PARAM_SET](params.md#param_set)
- [PARAM_GET](params.md#param_get)
- [PARAM_REPORT](params.md#param_report)

---

## 5. CMD 匹配

```text
CMD_REQUEST

+-----------------------------+
| CMD_REQUEST                 |
| Type = 0x31                 |
| FrameID = F3                |
+--------------+--------------+
               |
               v
+-----------------------------+
| CMD_RESPONSE                |
| Type = 0x32                 |
| request_frame_id = F3       |
+-----------------------------+
```

匹配字段：

```text
CMD_RESPONSE.request_frame_id = CMD_REQUEST.FrameID
CMD_RESPONSE.cmd_id = CMD_REQUEST.cmd_id
```

所有 CMD_REQUEST 都必须返回 CMD_RESPONSE。Host 发送 Type `0x31`，并等待 Type `0x32`。

相关帧：

- [CMD_REQUEST](cmd.md#cmd_request)
- [CMD_RESPONSE](cmd.md#cmd_response)

---

## 6. 接收检查顺序

接收端应按以下顺序处理：

```text
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
| Check Raw Length  |
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
| Parse Payload     |
+---------+---------+
          |
          v
+-------------------+
| Dispatch Type     |
+-------------------+
```

基础流程详见 [frame.md#receive-flow](frame.md#receive-flow)。

---

## 7. 错误处理

MCU 可以使用 [STATUS](runtime.md#status) 上报协议层错误：

```text
COBS 解码失败 -> STATUS(FRAME_DECODE_ERROR)
RawFrame 太短 -> STATUS(FRAME_DECODE_ERROR)
Magic 错误 -> STATUS(FRAME_DECODE_ERROR)
CRC 错误 -> STATUS(CRC_ERROR)
未知 Type -> STATUS(UNKNOWN_TYPE)
FrameID 为 0 -> STATUS(BAD_PAYLOAD)
DISCOVER 版本不支持 -> STATUS(VERSION_UNSUPPORTED)
DISCOVER 注册记录过大 -> STATUS(TOO_LARGE)
TX 忙或队列满 -> STATUS(BUSY) 或 STATUS(TX_DROP)
RX ring overflow -> STATUS(RX_OVERFLOW)
```

业务请求的错误响应：

| 原始帧 | 错误回复 |
|---|---|
| [PARAM_SET](params.md#param_set) | [PARAM_REPORT](params.md#param_report) |
| [PARAM_GET](params.md#param_get) | [PARAM_REPORT](params.md#param_report) |
| [CMD_REQUEST](cmd.md#cmd_request) | [CMD_RESPONSE](cmd.md#cmd_response) |

错误响应应设置合适的 [Status Code](common.md#status-code)。

---

## 8. 最大帧长度

协商后最大 RawFrame：

```text
peer_max_decoded_frame = min(host_max_decoded_frame, mcu_max_decoded_frame)
```

其中：

- `host_max_decoded_frame` 在 [DISCOVER](init.md#discover) 中发送。
- `mcu_max_decoded_frame` 在 [REGISTER_BEGIN](init.md#register_begin) 中发送。

发送方必须保证：

```text
raw_frame_len <= peer_max_decoded_frame
```

单帧规则：

```text
所有逻辑消息必须完整放入一个 RawFrame。
协议不定义跨帧重组机制。
发送方不得使用连续帧重组来传输一个逻辑消息的分片。
```

如果完整逻辑消息超过 `peer_max_decoded_frame`：

| 场景 | 处理 |
|---|---|
| REGISTER 记录过大 | 终止注册，发送 `STATUS(TOO_LARGE)` |
| PARAM_GET / PARAM_SET 响应过大 | 返回 `PARAM_REPORT(ERROR_ONLY, TOO_LARGE, item_count=0)` |
| LOG_REPORT / LOG_TEXT / 参数主动事件过大 | 拆成多条独立事件或丢弃并增加错误计数 |
| CMD_RESPONSE 过大 | 返回不携带 user_payload 的 `CMD_RESPONSE(status = TOO_LARGE)` |

COBS 编码缓冲区容量：

```c
encoded_max = raw_max + raw_max / 254 + 2;
```
