# LiteTune v0.5.0 Init and Register Specification

本文件定义初始化和注册模块，包括：

```text
DISCOVER
REGISTER_BEGIN
REGISTER_LOG_LAYOUT
REGISTER_PARAM_DESC
REGISTER_CMD_DESC
REGISTER_END
```

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [Feature Bitmask](common.md#feature-bitmask)
- [Value Type](common.md#value-type)
- [STATUS](runtime.md#status)

---

## 1. 初始化流程

```text
+------+                                +------+
| Host |                                | MCU  |
+------+                                +------+
   |                                      |
   | DISCOVER                             |
   |------------------------------------->|
   |                                      |
   | REGISTER_BEGIN                       |
   |<-------------------------------------|
   | REGISTER_LOG_LAYOUT                 |
   |<-------------------------------------|
   | REGISTER_PARAM_DESC                 |
   |<-------------------------------------|
   | REGISTER_CMD_DESC                   |
   |<-------------------------------------|
   | REGISTER_END                        |
   |<-------------------------------------|
   |                                      |
   |              READY                   |
```

初始化完成后，Host 才应发送：

```text
PARAM_SET
PARAM_GET
CMD_REQUEST
```

错误时 MCU 发送：

```text
STATUS(status_code)
```

---

## 2. DISCOVER

### 2.1 方向

```text
Host -> MCU
```

### 2.2 作用

```text
发现设备
协商协议版本
协商最大帧长度
协商 feature
请求 MCU 发送完整 REGISTER_* 序列
```

### 2.3 Type

```text
Type  = 0x01
```

### 2.4 完整帧结构图

```text
DISCOVER RawFrame

+----------+----------+----------------+------------------+----------+
| Magic    | Type     | FrameID        | DISCOVER Payload | CRC16    |
| u16      | 0x01     | u64            | variable         | u16      |
+----------+----------+----------------+------------------+----------+
```

### 2.5 Payload 结构图

```text
DISCOVER Payload

offset
0      1      2      3        5          9         11
+------+------+------+--------+----------+---------+----------+
| Maj  | Min  |Patch | MaxLen | Features | TO_ms   | HostName |
| u8   | u8   | u8   | u16    | u32      | u16     | str8     |
+------+------+------+--------+----------+---------+----------+
```

### 2.6 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `host_proto_major` | 当前为 `0` |
| 1 | `u8` | `host_proto_minor` | 当前为 `5` |
| 2 | `u8` | `host_proto_patch` | 当前为 `0` |
| 3 | `u16` | `host_max_decoded_frame` | Host 可接收最大 RawFrame |
| 5 | `u32` | `requested_features` | Host 请求功能，见 [Feature Bitmask](common.md#feature-bitmask) |
| 9 | `u16` | `response_timeout_ms` | Host 期望的业务响应超时；协议层不定义自动重发 |
| 11 | `str8` | `host_name` | Host 名称 |

### 2.7 处理规则

MCU 收到 DISCOVER 后：

```text
1. 检查协议版本。
2. 检查 host_max_decoded_frame。
3. 计算 peer_max_decoded_frame = min(host_max_decoded_frame, LT_RAW_FRAME_SIZE)。
4. 计算 enabled_features = requested_features & mcu_supported_features。
5. 检查所有 REGISTER record 是否能放入 peer_max_decoded_frame。
6. 如果成功，发送完整 REGISTER_* 序列。
7. 如果失败，发送 STATUS(status_code)，不发送 REGISTER_*。
```

错误示例：

| 场景 | STATUS |
|---|---|
| 版本不支持 | `VERSION_UNSUPPORTED` |
| REGISTER record 太大 | `TOO_LARGE` |
| MCU 注册尚未完成 | `NOT_READY` |
| TX 忙 | `BUSY` |
| DISCOVER payload 格式错误 | `BAD_PAYLOAD` |

---

## 3. REGISTER 总体结构

### 3.1 方向

```text
MCU -> Host
```

### 3.2 作用

REGISTER 让 Host 知道：

```text
设备显示名称
协议版本
启用功能
遥测 layout
参数列表
命令列表
```

### 3.3 Type

REGISTER 记录使用独立 RawFrame Type 分辨具体类型：

| Type | 名称 | 章节 |
|---:|---|---|
| `0x02` | `REGISTER_BEGIN` | [REGISTER_BEGIN](#register_begin) |
| `0x03` | `REGISTER_LOG_LAYOUT` | [REGISTER_LOG_LAYOUT](#register_log_layout) |
| `0x04` | `REGISTER_PARAM_DESC` | [REGISTER_PARAM_DESC](#register_param_desc) |
| `0x05` | `REGISTER_CMD_DESC` | [REGISTER_CMD_DESC](#register_cmd_desc) |
| `0x06` | `REGISTER_END` | [REGISTER_END](#register_end) |

### 3.4 行为规则

```text
1. 每次合法 DISCOVER 后，MCU 必须发送完整 REGISTER_* 序列。
2. Host 每次收到 REGISTER_BEGIN 后，清空已保存的注册信息。
3. Host 收到 REGISTER_END 后，使用本次 REGISTER 构建当前解析表。
4. Host 不跨 REGISTER 周期保留 pending request。
5. 每个 REGISTER_* RawFrame 必须携带一条完整注册记录。
```

单帧注册记录：

```text
REGISTER_BEGIN 完整描述设备显示名称、协议版本和注册总览。
每个 REGISTER_LOG_LAYOUT 完整描述一个 layout 的全部字段。
REGISTER_PARAM_DESC 完整描述全部参数。
REGISTER_CMD_DESC 完整描述全部命令。
REGISTER_END 表示注册结束。
```

规则：

```text
REGISTER_LOG_LAYOUT 应发送 layout_count 次；layout_count = 0 时不发送。
param_count = 0 时可省略 REGISTER_PARAM_DESC；若发送，则 param_count 必须为 0 且不携带 descriptor。
cmd_count = 0 时可省略 REGISTER_CMD_DESC；若发送，则 cmd_count 必须为 0 且不携带 descriptor。
任何 REGISTER 记录如果无法放入单个 RawFrame，MCU 不得发送部分内容，应终止注册并发送 STATUS(TOO_LARGE)。
```

### 3.5 Type 分发规则

```text
REGISTER_* 的具体 Payload 结构由 RawFrame.Type 决定。
Payload 中不包含额外的注册种类字段。
接收端必须按 RawFrame.Type 分发 REGISTER_BEGIN / REGISTER_LOG_LAYOUT / REGISTER_PARAM_DESC / REGISTER_CMD_DESC / REGISTER_END。
```

---

## 4. REGISTER_BEGIN

### 4.1 作用

注册设备显示名称、协议版本、启用功能和记录数量总览。

### 4.2 完整帧结构图

```text
REGISTER_BEGIN RawFrame

+----------+----------+----------------+------------------------+----------+
| Magic    | Type     | FrameID        | REGISTER_BEGIN Payload | CRC16    |
| u16      | 0x02     | u64            | variable               | u16      |
+----------+----------+----------------+------------------------+----------+
```

### 4.3 Payload 结构图

```text
REGISTER_BEGIN Payload

offset
0      1      2      3        5          9        10       12
+------+------+------+--------+----------+--------+---------+---------+
| Maj  | Min  |Patch |MaxLen  | Features |Layouts | Params  | Cmds    |
| u8   |u8    |u8    |u16     |u32       |u8      |u16      |u16      |
+------+------+------+--------+----------+--------+---------+---------+

offset
14
+-------------+
| DeviceName  |
| str8        |
+-------------+
```

### 4.4 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `mcu_proto_major` | 当前为 `0` |
| 1 | `u8` | `mcu_proto_minor` | 当前为 `5` |
| 2 | `u8` | `mcu_proto_patch` | 当前为 `0` |
| 3 | `u16` | `mcu_max_decoded_frame` | MCU 可接收最大 RawFrame |
| 5 | `u32` | `enabled_features` | 实际启用功能，见 [Feature Bitmask](common.md#feature-bitmask) |
| 9 | `u8` | `layout_count` | LOG layout 数量 |
| 10 | `u16` | `param_count` | 参数数量 |
| 12 | `u16` | `cmd_count` | 命令数量 |
| 14 | `str8` | `device_name` | 设备显示名称 |

`device_name` 只用于 UI 显示，不作为稳定身份。

---

## 5. REGISTER_LOG_LAYOUT

### 5.1 作用

注册 [LOG_REPORT](telemetry.md#log_report) 的 layout 和字段。Host 依赖它解析 packed telemetry。

### 5.2 完整帧结构图

```text
REGISTER_LOG_LAYOUT RawFrame

+----------+----------+----------------+-----------------------------+----------+
| Magic    | Type     | FrameID        | REGISTER_LOG_LAYOUT Payload | CRC16    |
| u16      | 0x03     | u64            | variable                    | u16      |
+----------+----------+----------------+-----------------------------+----------+
```

### 5.3 Payload 结构图

```text
REGISTER_LOG_LAYOUT Payload

offset
0          1              3            4
+----------+--------------+------------+---------------------+
|LayoutID  | Default_ms   | FieldCount | Field Descriptors   |
|u8        | u16          | u8         | variable            |
+----------+--------------+------------+---------------------+
```

### 5.4 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `layout_id` | Layout ID，见 [ID 规则](common.md#id-rules) |
| 1 | `u16` | `default_period_ms` | 默认周期；0 表示事件触发 |
| 3 | `u8` | `field_count` | 当前 layout 的字段总数 |
| 4 | variable | `field_descriptors` | 全部字段描述数组 |

### 5.5 Field Descriptor

```text
Field Descriptor

+-------------+-------------+-------------+-----------+
| field_id    | value_type  | name        | unit      |
| u16         | u8          | str8        | str8      |
+-------------+-------------+-------------+-----------+
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `field_id` | `u16` | 字段 ID，见 [ID 规则](common.md#id-rules) |
| `value_type` | `u8` | 见 [Value Type](common.md#value-type) |
| `name` | `str8` | 字段名，例如 `speed.current` |
| `unit` | `str8` | 单位，例如 `m/s`，可为空 |

规则：

```text
layout_id 使用 u8。
同一个 layout 内 field_id 必须唯一。
Packed LOG_REPORT 的字段顺序由 Field Descriptor 顺序决定。
```

### 5.6 单帧规则

```text
REGISTER_LOG_LAYOUT 必须在单个 RawFrame 内携带该 layout 的全部字段。
Host 应检查 field_count 等于实际解码出的 Field Descriptor 数量。
Host 应检查同一个 layout 内 field_id 唯一。
如果该 layout 的完整描述无法放入 peer_max_decoded_frame，则该 layout 不可注册，MCU 应终止注册并发送 STATUS(TOO_LARGE)。
```

---

## 6. REGISTER_PARAM_DESC

### 6.1 作用

注册参数。参数后续由 [PARAM_SET](params.md#param_set)、[PARAM_GET](params.md#param_get)、[PARAM_REPORT](params.md#param_report) 使用。

### 6.2 完整帧结构图

```text
REGISTER_PARAM_DESC RawFrame

+----------+----------+----------------+-----------------------------+----------+
| Magic    | Type     | FrameID        | REGISTER_PARAM_DESC Payload | CRC16    |
| u16      | 0x04     | u64            | variable                    | u16      |
+----------+----------+----------------+-----------------------------+----------+
```

### 6.3 Payload 结构图

```text
REGISTER_PARAM_DESC Payload

offset
0             2
+-------------+----------------------+
| ParamCount  | Param Descriptors    |
| u16         | variable             |
+-------------+----------------------+
```

### 6.4 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u16` | `param_count` | 参数总数 |
| 2 | variable | `param_descriptors` | 全部参数描述数组 |

规则：

```text
REGISTER_PARAM_DESC 必须在单个 RawFrame 内携带全部参数描述。
Host 应检查 param_count 等于实际解码出的 Param Descriptor 数量。
如果全部参数描述无法放入 peer_max_decoded_frame，则参数表不可注册，MCU 应终止注册并发送 STATUS(TOO_LARGE)。
```

### 6.5 Param Descriptor

```text
Param Descriptor

+----------+------------+--------+--------+
| param_id | value_type | name   | unit   |
| u16      | u8         | str8   | str8   |
+----------+------------+--------+--------+
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `param_id` | `u16` | 参数 ID，见 [ID 规则](common.md#id-rules) |
| `value_type` | `u8` | 见 [Value Type](common.md#value-type) |
| `name` | `str8` | 参数名，例如 `pid.kp` |
| `unit` | `str8` | 单位，例如 `rad/s`，可为空 |

规则：

```text
参数按 LiteTune PARAM 设计均可读写，REGISTER_PARAM_DESC 不提供 read/write flag。
min_value、max_value、default_value 等 UI 约束或默认值由 Host / 上位机配置或业务层管理，不在 REGISTER_PARAM_DESC 中传输。
当前值通过 PARAM_GET / PARAM_REPORT 获取，不放入 Param Descriptor。
```

---

## 7. REGISTER_CMD_DESC

### 7.1 作用

注册用户命令。命令后续由 [CMD](cmd.md#cmd) 使用。

### 7.2 完整帧结构图

```text
REGISTER_CMD_DESC RawFrame

+----------+----------+----------------+---------------------------+----------+
| Magic    | Type     | FrameID        | REGISTER_CMD_DESC Payload | CRC16    |
| u16      | 0x05     | u64            | variable                  | u16      |
+----------+----------+----------------+---------------------------+----------+
```

### 7.3 Payload 结构图

```text
REGISTER_CMD_DESC Payload

offset
0           2
+-----------+-------------------+
| CmdCount  | Cmd Descriptors   |
| u16       | variable          |
+-----------+-------------------+
```

### 7.4 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u16` | `cmd_count` | 命令总数 |
| 2 | variable | `cmd_descriptors` | 全部命令描述数组 |

规则：

```text
REGISTER_CMD_DESC 必须在单个 RawFrame 内携带全部命令描述。
Host 应检查 cmd_count 等于实际解码出的 Cmd Descriptor 数量。
如果全部命令描述无法放入 peer_max_decoded_frame，则命令表不可注册，MCU 应终止注册并发送 STATUS(TOO_LARGE)。
```

### 7.5 Cmd Descriptor

```text
Cmd Descriptor

+----------+-----------+--------+
| cmd_id   | cmd_flags | name   |
| u16      | u8        | str8   |
+----------+-----------+--------+
```

### 7.6 cmd_flags

| Bit | 名称 | 说明 |
|---:|---|---|
| 0 | `HOST_TO_MCU` | Host 可向 MCU 发送 CMD_REQUEST |
| 1-7 | reserved | 保留，必须为 0 |

---

## 8. REGISTER_END

### 8.1 作用

表示 REGISTER 过程结束。Host 收到 REGISTER_END 后，才认为本次注册信息完整。

### 8.2 完整帧结构图

```text
REGISTER_END RawFrame

+----------+----------+----------------+----------------------+----------+
| Magic    | Type     | FrameID        | REGISTER_END Payload | CRC16    |
| u16      | 0x06     | u64            | 0 bytes              | u16      |
+----------+----------+----------------+----------------------+----------+
```

### 8.3 Payload

```text
REGISTER_END Payload 长度为 0。
```
