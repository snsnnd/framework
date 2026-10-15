# LiteTune v0.5.0 CMD Specification

本文件定义 CMD 模块。

核心帧 Type：

```text
CMD_REQUEST  = 0x31
CMD_RESPONSE = 0x32
```

CMD 用于承载用户自定义命令请求和响应。

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [REGISTER_CMD_DESC](init.md#register_cmd_desc)
- [可靠性](reliability.md)

---

## 1. CMD 总览

### 1.1 方向

```text
CMD_REQUEST:  Host -> MCU
CMD_RESPONSE: MCU -> Host
```

### 1.2 Type

```text
CMD_REQUEST  = 0x31
CMD_RESPONSE = 0x32
```

`CMD_REQUEST` 和 `CMD_RESPONSE` 使用独立 Type。CMD Payload 中不携带 op 字段。

### 1.3 作用

承载用户自定义命令请求和响应。例如：

```text
encoder.zero
imu.calibrate
motor.test
enter_bootloader
params.save
params.load
params.reset_default
controller.start_step_response
```

### 1.4 设计原则

```text
LiteTune 核心只解析 cmd_id、request_frame_id 和 status。
user_payload 由用户自定义。
命令名称和 cmd_flags 由 REGISTER_CMD_DESC 注册。
```

---

## 2. CMD_REQUEST

### 2.1 作用

Host 请求 MCU 执行命令。


所有 `CMD_REQUEST` 都必须返回 `CMD_RESPONSE`。即使命令没有返回值，也返回：

```text
CMD_RESPONSE(status = OK, user_payload = empty)
```

### 2.2 完整帧结构图

```text
CMD_REQUEST RawFrame

+----------+----------+----------------+---------------------+----------+
| Magic    | Type     | FrameID        | CMD_REQUEST Payload | CRC16    |
| u16      | 0x31     | u64            | variable            | u16      |
+----------+----------+----------------+---------------------+----------+
```

### 2.3 Payload 结构图

```text
CMD_REQUEST Payload

offset
0          2
+----------+----------------+
| cmd_id   | user_payload   |
| u16      | variable       |
+----------+----------------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u16` | `cmd_id` | 命令 ID |
| 2 | variable | `user_payload` | 用户自定义请求数据 |

最小 Payload 长度：

```text
2 bytes
```

最小 RawFrame 长度：

```text
13 + 2 = 15 bytes
```

---

## 3. CMD_RESPONSE

### 3.1 作用

MCU 返回 Host 发起的 CMD_REQUEST 的执行结果。


### 3.2 完整帧结构图

```text
CMD_RESPONSE RawFrame

+----------+----------+----------------+----------------------+----------+
| Magic    | Type     | FrameID        | CMD_RESPONSE Payload | CRC16    |
| u16      | 0x32     | u64            | variable             | u16      |
+----------+----------+----------------+----------------------+----------+
```

### 3.3 Payload 结构图

```text
CMD_RESPONSE Payload

offset
0                         8          10         11
+-------------------------+----------+----------+----------------+
| request_frame_id        | cmd_id   | status   | user_payload   |
| u64                     | u16      | u8       | variable       |
+-------------------------+----------+----------+----------------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u64` | `request_frame_id` | 对应 CMD_REQUEST 的 FrameID |
| 8 | `u16` | `cmd_id` | 命令 ID |
| 10 | `u8` | `status` | 见 [Status Code](common.md#status-code) |
| 11 | variable | `user_payload` | 用户自定义返回数据 |

规则：

```text
CMD_RESPONSE.request_frame_id = CMD_REQUEST.FrameID
CMD_RESPONSE.cmd_id = CMD_REQUEST.cmd_id
```

最小 Payload 长度：

```text
8 + 2 + 1 = 11 bytes
```

最小 RawFrame 长度：

```text
13 + 11 = 24 bytes
```

---

## 4. 错误处理

错误也用 `CMD_RESPONSE`：

```text
命令不存在:
  CMD_RESPONSE(status = NOT_FOUND)

payload 错误:
  CMD_RESPONSE(status = BAD_PAYLOAD)

callback 返回失败:
  CMD_RESPONSE(status = EXEC_ERROR 或 callback 返回状态)

```

如果 response payload 过大，返回不携带 user_payload 的响应：

```text
CMD_RESPONSE(status = TOO_LARGE, user_payload = empty)
```

---

## 5. CMD callback 建议

建议 MCU lib 中 CMD callback 预留 response payload：

```c
typedef lt_status_t (*lt_cmd_callback_t)(
    const uint8_t *req_payload,
    uint16_t req_len,
    uint8_t *resp_payload,
    uint16_t resp_cap,
    uint16_t *resp_len,
    void *user_ctx
);
```

如果命令不需要返回数据：

```c
*resp_len = 0;
return LT_STATUS_OK;
```

---

## 6. 用 CMD 处理参数持久化

LiteTune 核心不定义参数持久化。用户可以注册如下命令名称：

```text
name = params.save
name = params.load
name = params.reset_default
```

流程：

```text
Host -> MCU:
  CMD_REQUEST
  Type = 0x31
  cmd_id = <params.save 对应的 u16 ID>

MCU -> Host:
  CMD_RESPONSE
  Type = 0x32
  request_frame_id = 原请求 FrameID
  cmd_id = <params.save 对应的 u16 ID>
  status = OK
```

这些命令的具体 payload 和存储行为由用户实现。
