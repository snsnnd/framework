# LiteTune v0.5.0 Common Specification

本文件定义 LiteTune 的公共约定。所有其他模块都依赖本文件。

相关文档：

- [帧层规范](frame.md)
- [初始化与注册](init.md)
- [遥测模块](telemetry.md)
- [参数模块](params.md)
- [命令模块](cmd.md)
- [运行辅助](runtime.md)

---

## 1. 基础规则

```text
1. 所有多字节字段均为 little-endian。
2. 所有字符串均为 str8：u8 len + UTF-8 bytes。
3. 所有字段按字节连续编码，无 padding。
4. 不得直接发送 C struct 内存。
5. 帧边界由 COBS + 0x00 处理，详见 frame.md。
6. FrameID 是发送方生成的不透明 u64 ID。
7. PARAM_SET / PARAM_GET 的响应统一使用 PARAM_REPORT。
8. 所有 CMD_REQUEST 必须使用 CMD_RESPONSE 响应。
9. STATUS 是 MCU 到 Host 的异步状态通知。
10. 参数持久化由用户处理，不属于 LiteTune 核心协议。
```

---

## 2. 字节序

所有多字节字段均为 little-endian。

```text
u16 0xA55A -> 5A A5
u32 0x12345678 -> 78 56 34 12
u64 0x0102030405060708 -> 08 07 06 05 04 03 02 01
```

---

## 3. 基础类型

| 类型 | 大小 | 说明 |
|---|---:|---|
| `u8` | 1 byte | 无符号 8 位整数 |
| `i8` | 1 byte | 有符号 8 位整数 |
| `u16` | 2 bytes | little-endian |
| `i16` | 2 bytes | little-endian |
| `u32` | 4 bytes | little-endian |
| `i32` | 4 bytes | little-endian |
| `u64` | 8 bytes | little-endian |
| `i64` | 8 bytes | little-endian |
| `f32` | 4 bytes | IEEE-754 single precision |
| `f64` | 8 bytes | IEEE-754 double precision |
| `str8` | 1 + N bytes | `u8 len` + UTF-8 bytes |
| `bytes8` | 1 + N bytes | `u8 len` + raw bytes |

---

## 4. 字符串：str8

```text
str8

+----------+----------------------+
| len: u8  | content: len bytes   |
+----------+----------------------+
```

规则：

```text
len 表示 UTF-8 字节数，不是字符数。
content 不包含 '\0'。
允许 len = 0。
最大长度 255 bytes。
接收端不得把 content 直接当作 C 字符串使用。
```

---

## 5. 版本号

LiteTune 使用三段版本号：

```text
major.minor.patch
```

当前版本：

```text
0.5.0
```

编码方式：

```text
proto_major = 0
proto_minor = 5
proto_patch = 0
```

版本字段出现在：

- [DISCOVER](init.md#discover)
- [REGISTER_BEGIN](init.md#register_begin)

---

## 6. Magic

LiteTune 固定 Magic：

```text
Magic = 0xA55A
```

RawFrame 中实际字节顺序为：

```text
5A A5
```

Magic 错误的帧必须丢弃。详见 [帧层错误处理](frame.md#error-handling-basic)。

---

## 7. Feature Bitmask

`requested_features` 和 `enabled_features` 均为 `u32`。

| Bit | 名称 | 说明 |
|---:|---|---|
| 0 | `LOG_PACKED` | 支持 [LOG_REPORT packed single](telemetry.md#log_report_packed_single) |
| 1 | `PARAM_GET` | 支持 [PARAM_GET](params.md#param_get) |
| 2 | `PARAM_SET` | 支持 [PARAM_SET](params.md#param_set) |
| 3 | `CMD` | 支持 [CMD_REQUEST / CMD_RESPONSE](cmd.md#cmd) |
| 4 | `LOG_TEXT` | 支持 [LOG_TEXT](runtime.md#log_text) |
| 5-31 | reserved | 保留 |

协商规则：

```text
Host 在 DISCOVER 中发送 requested_features。
MCU 在 REGISTER_BEGIN 中返回 enabled_features。
enabled_features = requested_features & mcu_supported_features。
STATUS 是核心帧，不进入 Feature Bitmask。
```

LiteTune 不定义 `PARAM_PERSIST`。参数持久化由用户应用层处理。

---

## 8. Value Type

[REGISTER_LOG_LAYOUT](init.md#register_log_layout) 和 [REGISTER_PARAM_DESC](init.md#register_param_desc) 使用统一 `value_type`。

| Type ID | 名称 | 编码 |
|---:|---|---|
| `0x00` | invalid | 保留 |
| `0x01` | bool | `u8`, 0=false, nonzero=true |
| `0x02` | u8 | 1 byte |
| `0x03` | i8 | 1 byte |
| `0x04` | u16 | 2 bytes LE |
| `0x05` | i16 | 2 bytes LE |
| `0x06` | u32 | 4 bytes LE |
| `0x07` | i32 | 4 bytes LE |
| `0x08` | u64 | 8 bytes LE |
| `0x09` | i64 | 8 bytes LE |
| `0x0A` | f32 | 4 bytes LE |
| `0x0B` | f64 | 8 bytes LE |
| `0x0C` | string | `str8` |
| `0x0D` | bytes | `bytes8` |
| `0x0E` | enum_u8 | `u8` |

---

## 9. Status Code

状态码为 `u8`。

| 值 | 名称 | 说明 |
|---:|---|---|
| `0x00` | `OK` | 成功 |
| `0x01` | `ACCEPTED` | 已接收，可能异步处理 |
| `0x02` | `PARTIAL_OK` | 部分成功 |
| `0x03` | reserved | 保留 |
| `0x10` | `VERSION_UNSUPPORTED` | 版本不支持 |
| `0x11` | `UNKNOWN_TYPE` | 未知 Type |
| `0x12` | reserved | 保留 |
| `0x13` | `BAD_PAYLOAD` | Payload 错误 |
| `0x14` | `NOT_FOUND` | ID 不存在 |
| `0x15` | `TYPE_MISMATCH` | 类型不匹配 |
| `0x16` | `RANGE_ERROR` | 参数越界 |
| `0x17` | reserved | 保留 |
| `0x18` | `BUSY` | 设备忙 |
| `0x19` | `STORAGE_ERROR` | 存储错误，用户层可选择使用 |
| `0x1A` | `DENIED` | 拒绝执行 |
| `0x1B` | `EXEC_ERROR` | 执行失败 |
| `0x1C` | `TOO_LARGE` | 数据过大 |
| `0x1D` | `UNSUPPORTED` | 不支持 |
| `0x1E` | `TIMEOUT` | 超时 |
| `0x1F` | `CONFLICT` | 状态冲突 |
| `0x20` | `NOT_READY` | 尚未准备好 |
| `0x21` | `INVALID_STATE` | 当前状态不允许 |
| `0x22` | `FRAME_DECODE_ERROR` | COBS 解码失败、RawFrame 太短或 Magic 错误 |
| `0x23` | `CRC_ERROR` | CRC 校验失败 |
| `0x24` | `RX_OVERFLOW` | RX ring overflow |
| `0x25` | `TX_DROP` | TX 队列满或低优先级帧被丢弃 |
| `0x7F` | `UNKNOWN_ERROR` | 未知错误 |
| `0x80-0xFF` | user-defined | 用户自定义 |

---

## 10. Type 总表

| Type | 名称 | 方向 | 模块 | 说明 |
|---:|---|---|---|---|
| `0x00` | invalid | - | - | 保留 |
| `0x01` | `DISCOVER` | Host -> MCU | [init](init.md#discover) | 初始化、协商 |
| `0x02` | `REGISTER_BEGIN` | MCU -> Host | [init](init.md#register_begin) | 注册开始、设备信息和记录总览 |
| `0x03` | `REGISTER_LOG_LAYOUT` | MCU -> Host | [init](init.md#register_log_layout) | 注册一个遥测 layout |
| `0x04` | `REGISTER_PARAM_DESC` | MCU -> Host | [init](init.md#register_param_desc) | 注册全部参数描述 |
| `0x05` | `REGISTER_CMD_DESC` | MCU -> Host | [init](init.md#register_cmd_desc) | 注册全部命令描述 |
| `0x06` | `REGISTER_END` | MCU -> Host | [init](init.md#register_end) | 注册结束 |
| `0x07` | `STATUS` | MCU -> Host | [runtime](runtime.md#status) | 错误/状态上报 |
| `0x08-0x10` | reserved | - | - | 保留 |
| `0x11` | `LOG_REPORT` | MCU -> Host | [telemetry](telemetry.md#log_report) | 单样本遥测数据 |
| `0x12` | `LOG_TEXT` | MCU -> Host | [runtime](runtime.md#log_text) | 文本日志 |
| `0x21` | `PARAM_SET` | Host -> MCU | [params](params.md#param_set) | 设置参数 |
| `0x22` | `PARAM_GET` | Host -> MCU | [params](params.md#param_get) | 读取参数 |
| `0x23` | `PARAM_REPORT` | MCU -> Host | [params](params.md#param_report) | 参数响应 / 参数事件 |
| `0x31` | `CMD_REQUEST` | Host -> MCU | [cmd](cmd.md#cmd_request) | 自定义命令请求 |
| `0x32` | `CMD_RESPONSE` | MCU -> Host | [cmd](cmd.md#cmd_response) | 自定义命令响应 |
| `0x33-0x3F` | reserved | - | - | 保留 |
| `0x40-0x7F` | project-specific | 双向 | 用户 | 项目私有扩展 |
| `0x80-0xFF` | reserved | - | - | 保留 |

---

## 11. ID 分配规则

### 11.1 layout_id

```text
u8
0x00 reserved
0x01-0xFE valid
0xFF reserved
```

### 11.2 field_id

```text
u16
0x0000 reserved
0x0001-0xFFFE valid
0xFFFF reserved
```

### 11.3 param_id

```text
u16
0x0000 reserved
0x0001-0xFFFE valid
0xFFFF reserved
```

### 11.4 cmd_id

```text
u16
0x0000 reserved
0x0001-0xFFFE valid
0xFFFF reserved
```

规则：

```text
1. 同一次 REGISTER 周期内 ID 必须唯一且稳定。
2. Host 收到新的 REGISTER_BEGIN 后，以本次 REGISTER 提供的 ID 映射为准。
3. 用户扩展 ID 应避开 LiteTune 保留值。
```
