# LiteTune v0.5.0 Parameters Specification

本文件定义参数模块，包括：

```text
PARAM_SET
PARAM_GET
PARAM_REPORT
```

参数由 [REGISTER_PARAM_DESC](init.md#register_param_desc) 注册。

相关文档：

- [公共约定](common.md)
- [RawFrame](frame.md#rawframe)
- [Value Type](common.md#value-type)
- [REGISTER_PARAM_DESC](init.md#register_param_desc)

---

## 1. 模块边界

LiteTune 参数模块只负责：

```text
设置参数值
读取参数值
返回参数操作结果
主动通知参数变化
```

LiteTune 参数模块不负责：

```text
保存到 Flash
从 Flash 加载
EEPROM 模拟
参数恢复默认
断电保存策略
```

如果需要持久化，建议通过 [CMD](cmd.md) 承载：

```text
cmd_id = params.save
cmd_id = params.load
cmd_id = params.reset_default
```

---

## 2. 请求响应模型

```text
PARAM_SET / PARAM_GET

+-----------------------------+
| PARAM_SET or PARAM_GET      |
| FrameID = F                 |
+--------------+--------------+
               |
               v
+-----------------------------+
| PARAM_REPORT                |
| request_frame_id = F        |
+-----------------------------+
```

业务结果必须由 `PARAM_REPORT` 返回。

---

## 3. PARAM_SET

### 3.1 方向

```text
Host -> MCU
```

### 3.2 作用

设置一个或多个参数。

### 3.3 Type

```text
Type  = 0x21
```

### 3.4 完整帧结构图

```text
PARAM_SET RawFrame

+----------+----------+----------------+-------------------+----------+
| Magic    | Type     | FrameID        | PARAM_SET Payload | CRC16    |
| u16      | 0x21     | u64            | variable          | u16      |
+----------+----------+----------------+-------------------+----------+
```

### 3.5 Payload 结构图

```text
PARAM_SET Payload

offset
0
+--------+----------------+----------------+------+
| count  | item 0         | item 1         | ...  |
| u8     | variable       | variable       |      |
+--------+----------------+----------------+------+
```

字段表：

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u8` | `count` | 本帧携带参数数量，必须 > 0 |
| 1 | variable | `items` | 参数设置项数组 |

PARAM_SET item：

```text
PARAM_SET Item

+------------+------------------------------+
| param_id   | value                        |
| u16        | by registered value_type     |
+------------+------------------------------+
```

### 3.6 原子性

`PARAM_SET` 必须按原子操作处理：

```text
1. MCU 应先解析全部 item。
2. MCU 应先校验全部 item。
3. 只有全部 item 合法时，才应用全部修改。
4. 任意 item 失败时，必须不应用任何 item。
5. 返回 PARAM_REPORT，报告当前值和错误状态。
```

失败时的报告规则：

```text
overall_status = 首个失败原因，或 BAD_PAYLOAD。
每个 item 的 item_status 给出该 item 的校验状态。
如果 overall_status != OK，则即使某个 item_status = OK，也只表示该 item 校验通过，不表示已应用。
```

### 3.7 响应

MCU 必须返回 [PARAM_REPORT](#param_report)：

```text
PARAM_REPORT.request_frame_id = PARAM_SET.FrameID
PARAM_REPORT.report_kind = RESPONSE_TO_SET
```

错误也使用 `PARAM_REPORT` 表达。

---

## 4. PARAM_GET

### 4.1 方向

```text
Host -> MCU
```

### 4.2 作用

读取参数。

### 4.3 Type

```text
Type  = 0x22
```

### 4.4 完整帧结构图

```text
PARAM_GET RawFrame

+----------+----------+----------------+-------------------+----------+
| Magic    | Type     | FrameID        | PARAM_GET Payload | CRC16    |
| u16      | 0x22     | u64            | variable          | u16      |
+----------+----------+----------------+-------------------+----------+
```

### 4.5 Payload 结构图

```text
PARAM_GET Payload

offset
0             1
+-------------+--------+------------+------------+------+
| query_mode  | count  | param_id 0 | param_id 1 | ...  |
| u8          | u8     | u16        | u16        |      |
+-------------+--------+------------+------------+------+
```

`query_mode`：

| 值 | 名称 | 说明 |
|---:|---|---|
| `0x00` | `BY_ID` | 按 param_id 读取 |
| `0x01` | `ALL` | 读取全部参数 |
| `0x02-0x7F` | reserved | 保留 |
| `0x80-0xFF` | user-defined | 用户扩展 |

规则：

```text
query_mode = BY_ID:
  count 必须 > 0。
  后续携带 count 个 param_id。

query_mode = ALL:
  count 应为 0。

```

### 4.6 响应

MCU 必须返回 [PARAM_REPORT](#param_report)：

```text
PARAM_REPORT.request_frame_id = PARAM_GET.FrameID
PARAM_REPORT.report_kind = RESPONSE_TO_GET
```

错误也使用 `PARAM_REPORT` 表达。

---

## 5. PARAM_REPORT

### 5.1 方向

```text
MCU -> Host
```

### 5.2 作用

用于：

```text
响应 PARAM_SET
响应 PARAM_GET
主动通知参数变化
报告参数错误
```

### 5.3 Type

```text
Type = 0x23
```

作为响应时：

```text
request_frame_id = 原请求 FrameID
```

主动事件时：

```text
request_frame_id = 0
```

单帧规则：

```text
每个 PARAM_REPORT 必须携带完整报告。
Host 收到一个 PARAM_REPORT 后即可处理，不等待后续帧，也不执行跨帧重组。
```

### 5.4 完整帧结构图

```text
PARAM_REPORT RawFrame

+----------+----------+----------------+----------------------+----------+
| Magic    | Type     | FrameID        | PARAM_REPORT Payload | CRC16    |
| u16      | 0x23     | u64            | variable             | u16      |
+----------+----------+----------------+----------------------+----------+
```

### 5.5 Payload 结构图

```text
PARAM_REPORT Payload

offset
0                         8              9                 10
+-------------------------+--------------+-----------------+-------------+
| request_frame_id        | report_kind  | overall_status  | item_count  |
| u64                     | u8           | u8              | u16         |
+-------------------------+--------------+-----------------+-------------+

offset
12
+----------------+----------------+------+
| item 0         | item 1         | ...  |
| variable       | variable       |      |
+----------------+----------------+------+
```

### 5.6 Payload 字段

| Offset | 类型 | 字段 | 说明 |
|---:|---|---|---|
| 0 | `u64` | `request_frame_id` | 对应请求 FrameID；主动事件为 0 |
| 8 | `u8` | `report_kind` | 报告类型 |
| 9 | `u8` | `overall_status` | 整体状态，见 [Status Code](common.md#status-code) |
| 10 | `u16` | `item_count` | item 数 |
| 12 | variable | `items` | 全部 item 数组 |

`report_kind`：

| 值 | 名称 | 说明 |
|---:|---|---|
| `0x00` | `RESPONSE_TO_SET` | `PARAM_SET` 响应；`request_frame_id` 为原请求 FrameID |
| `0x01` | `RESPONSE_TO_GET` | `PARAM_GET` 响应；`request_frame_id` 为原请求 FrameID |
| `0x02` | `PARAM_CHANGED_EVENT` | 参数变化事件；`request_frame_id = 0` |
| `0x03` | `ERROR_ONLY` | 错误报告，按场景关联原请求或设为 0 |
| `0x04-0x7F` | reserved | 保留 |
| `0x80-0xFF` | user-defined | 用户自定义 |

### 5.7 PARAM_REPORT Item

```text
PARAM_REPORT Item

+------------+---------------+------------------------------+
| param_id   | item_status   | value                        |
| u16        | u8            | by registered value_type     |
+------------+---------------+------------------------------+
```

规则：

```text
PARAM_REPORT Item 只用于已注册、可确定 value_type 的参数，并携带 value。
PARAM_GET 成功时，value 为读取到的当前值。
PARAM_SET 成功时，value 为实际生效值。
PARAM_SET 失败但参数已注册时，value 为该参数当前值；由于 PARAM_SET 为原子操作，失败时所有参数均未被修改。
如果错误导致无法确定 value_type 或当前值，使用 ERROR_ONLY 且 item_count = 0。
如果 MCU 对参数进行了限幅且设置成功，应返回限幅后的实际值。
```

### 5.8 单帧与过大数据

```text
PARAM_REPORT 是完整单帧报告。
Host 不维护 PARAM_REPORT 重组状态。
```

如果正常响应无法放入 `peer_max_decoded_frame`，MCU 必须返回错误报告：

```text
PARAM_REPORT:
  request_frame_id = 原请求 FrameID
  report_kind = ERROR_ONLY
  overall_status = TOO_LARGE
  item_count = 0
```

规则：

```text
PARAM_GET query_mode = ALL 可能因为结果过大返回 TOO_LARGE。
Host 收到 TOO_LARGE 后，应改用多次独立的 PARAM_GET BY_ID 请求，并减少单次请求的 param_id 数量。
如果 PARAM_SET 的正常结果报告无法放入单帧，MCU 不应应用修改，应返回 ERROR_ONLY + TOO_LARGE。
主动 PARAM_CHANGED_EVENT 如果一次携带过多 item，MCU 应拆成多条独立事件；每条事件都是完整 PARAM_REPORT。
```

---

## 6. 错误处理

如果 `PARAM_SET` payload 格式错误：

```text
PARAM_REPORT:
  request_frame_id = request.FrameID
  report_kind = ERROR_ONLY
  overall_status = BAD_PAYLOAD
  item_count = 0
```

如果 `PARAM_SET` 中任意参数校验失败：

```text
不应用任何参数修改。
overall_status = 首个失败原因，例如 NOT_FOUND / TYPE_MISMATCH / RANGE_ERROR / ...
```

如果所有失败 item 都能确定已注册参数和当前值，每个 item 的 `item_status` 给出对应 item 的校验状态。
如果任一失败 item 无法确定 value_type 或当前值，返回 `ERROR_ONLY` 且 `item_count = 0`。

`PARAM_SET` 为原子操作，不使用 `PARTIAL_OK` 表示部分成功。
