# API 参考

本文档列出 LiteTune MCU Library 的全部公开函数、类型和常量。

## 1. 公开函数

### 初始化与注册

```c
lt_status_t lt_init(const lt_config_t *config);
```
初始化库。必须在所有其他 API 之前调用。成功后进入 `REGISTERING` 状态。

| 参数 | 说明 |
|---|---|
| `config` | 配置结构体指针，包含发送回调、FrameID 生成器、设备名和 Feature 声明 |

| 返回值 | 含义 |
|---|---|
| `LT_STATUS_OK` | 初始化成功 |
| `LT_STATUS_BAD_PAYLOAD` | `config`、`send` 或 `next_frame_id` 为 NULL |

---

```c
lt_status_t lt_register_log(const lt_log_registry_t *registry);
```
注册遥测 layout 表。只能在 `REGISTERING` 状态调用，同一类注册表只能注册一次。

---

```c
lt_status_t lt_register_param(const lt_param_registry_t *registry);
```
注册参数描述表。只能在 `REGISTERING` 状态调用。

---

```c
lt_status_t lt_register_cmd(const lt_cmd_registry_t *registry);
```
注册命令描述表。只能在 `REGISTERING` 状态调用。

---

```c
lt_status_t lt_register_complete(void);
```
完成注册阶段。校验所有已注册的描述表，检查所有注册记录是否能放入 `LT_RAW_FRAME_SIZE`。成功后进入 `WAIT_DISCOVER` 状态。

| 返回值 | 含义 |
|---|---|
| `LT_STATUS_OK` | 注册校验通过 |
| `LT_STATUS_INVALID_STATE` | 当前不在 `REGISTERING` 状态 |
| `LT_STATUS_TOO_LARGE` | 某注册记录超出本地帧容量 |
| `LT_STATUS_BAD_PAYLOAD` | 注册表内容无效（如重复 ID、无效类型） |
| `LT_STATUS_CONFLICT` | 同类注册表重复注册 |

### 主循环

```c
void lt_process(void);
```
主循环驱动函数。在 `WAIT_DISCOVER` 或 `CONNECTED` 状态下，依次处理接收帧和发送队列。必须在主循环中周期性调用。

在 `UNINIT` 或 `REGISTERING` 状态下调用无效果。

### 接收与发送

```c
lt_status_t lt_rx_from_isr(const void *data, uint16_t len);
```
ISR 安全的接收入口。将收到的原始字节写入内部环形缓冲区，不做任何解码或业务处理。适合在 UART 接收中断、DMA 完成回调等场景中调用。

| 返回值 | 含义 |
|---|---|
| `LT_STATUS_OK` | 成功写入 |
| `LT_STATUS_NOT_READY` | 库尚未完成初始化 |
| `LT_STATUS_BAD_PAYLOAD` | `data` 为 NULL 但 `len > 0` |
| `LT_STATUS_RX_OVERFLOW` | 缓冲区已满，数据被丢弃 |

---

```c
void lt_send_complete(void);
```
通知库底层发送已完成。必须在 `lt_config_t.send` 启动的传输完成后调用（如 DMA 发送完成中断中）。调用后库才会继续发送下一批排队数据。

### 遥测

```c
lt_status_t lt_log_report(uint8_t layout_id);
```
发送一次遥测报告。读取指定 layout 中各字段的当前值，打包后发送。仅在 `CONNECTED` 状态且 `LT_FEATURE_LOG_PACKED` 已启用时可用。

详见 [telemetry.md](telemetry.md)。

### 文本日志

```c
lt_status_t lt_log_text(uint8_t level, const char *text);
```
发送一条文本日志。仅在 `CONNECTED` 状态且 `LT_FEATURE_LOG_TEXT` 已启用时可用。

| 参数 | 说明 |
|---|---|
| `level` | 日志等级，使用 `LT_LOG_LEVEL_*` 常量 |
| `text` | UTF-8 字符串，最长 255 字节 |

详见 [runtime.md](runtime.md)。

## 2. 配置类型

```c
typedef lt_status_t (*lt_send_fn_t)(const void *data, uint16_t len);
```
底层发送回调。库调用此函数发送编码后的数据。成功返回 `LT_STATUS_OK`。

```c
typedef lt_frame_id_t (*lt_next_frame_id_fn_t)(void);
```
FrameID 生成回调。每次调用必须返回一个非零的唯一 `uint64_t`。最简单的实现是自增计数器。

```c
typedef struct {
    lt_send_fn_t send;
    lt_next_frame_id_fn_t next_frame_id;
    const char *device_name;
    uint32_t mcu_supported_features;
} lt_config_t;
```

| 字段 | 说明 |
|---|---|
| `send` | 底层发送回调（必须） |
| `next_frame_id` | FrameID 生成器（必须） |
| `device_name` | 设备名称，仅用于 UI 显示 |
| `mcu_supported_features` | MCU 支持的 Feature bitmask，用 `LT_FEATURE_*` 组合 |

## 3. 注册结构体

### 遥测注册

```c
typedef struct {
    lt_field_id_t field_id;     /* 字段 ID (1-0xFFFE) */
    uint8_t value_type;         /* LT_VALUE_* 类型 */
    const char *name;           /* 字段名 */
    const char *unit;           /* 单位（可为 "" 或 NULL） */
    const void *value_ptr;      /* 指向当前值的指针，lt_log_report() 时读取 */
} lt_log_field_desc_t;

typedef struct {
    lt_layout_id_t layout_id;   /* Layout ID (1-0xFE) */
    uint16_t default_period_ms; /* 建议上报周期 */
    uint8_t field_count;        /* 字段数量 */
    const lt_log_field_desc_t *fields;
} lt_log_layout_desc_t;

typedef struct {
    uint8_t layout_count;       /* layout 数量 */
    const lt_log_layout_desc_t *layouts;
} lt_log_registry_t;
```

详见 [telemetry.md](telemetry.md)。

### 参数注册

```c
typedef struct {
    lt_param_id_t param_id;     /* 参数 ID (1-0xFFFE) */
    uint8_t value_type;         /* LT_VALUE_* 类型 */
    const char *name;           /* 参数名 */
    const char *unit;           /* 单位（可为 "" 或 NULL） */
    void *value_ptr;            /* 指向参数值的指针 */
    uint32_t flags;             /* 本地策略位 LT_PARAM_FLAG_* */
} lt_param_desc_t;
```

```c
typedef struct {
    uint16_t param_count;
    const lt_param_desc_t *params;
} lt_param_registry_t;
```

详见 [params.md](params.md)。

### 命令注册

```c
typedef lt_status_t (*lt_cmd_callback_t)(
    const uint8_t *req_payload,   /* 请求 payload */
    uint16_t req_len,             /* 请求长度 */
    uint8_t *resp_payload,        /* 响应写入缓冲区 */
    uint16_t resp_cap,            /* 响应缓冲区容量 */
    uint16_t *resp_len,           /* 实际响应长度 */
    void *user_ctx                /* 用户上下文 */
);
```

```c
typedef struct {
    lt_cmd_id_t cmd_id;         /* 命令 ID (1-0xFFFE) */
    uint8_t cmd_flags;          /* LT_CMD_FLAG_HOST_TO_MCU 等 */
    const char *name;           /* 命令名 */
    lt_cmd_callback_t callback; /* 命令处理函数 */
    void *user_ctx;             /* 传递给 callback 的用户上下文 */
} lt_cmd_desc_t;
```

```c
typedef struct {
    uint16_t cmd_count;
    const lt_cmd_desc_t *cmds;
} lt_cmd_registry_t;
```

详见 [cmd.md](cmd.md)。

## 4. 枚举与常量

### 状态码 `lt_status_t`

成功：

| 值 | 名称 | 含义 |
|---|---|---|
| `0x00` | `LT_STATUS_OK` | 操作成功 |
| `0x01` | `LT_STATUS_ACCEPTED` | 已接受 |
| `0x02` | `LT_STATUS_PARTIAL_OK` | 部分成功 |

错误：

| 值 | 名称 | 含义 |
|---|---|---|
| `0x10` | `LT_STATUS_VERSION_UNSUPPORTED` | 协议版本不兼容 |
| `0x11` | `LT_STATUS_UNKNOWN_TYPE` | 未知帧类型 |
| `0x13` | `LT_STATUS_BAD_PAYLOAD` | Payload 格式错误 |
| `0x14` | `LT_STATUS_NOT_FOUND` | 请求的参数或命令不存在 |
| `0x15` | `LT_STATUS_TYPE_MISMATCH` | 值类型不匹配 |
| `0x16` | `LT_STATUS_RANGE_ERROR` | 值超出范围 |
| `0x18` | `LT_STATUS_BUSY` | 设备忙 |
| `0x19` | `LT_STATUS_STORAGE_ERROR` | 存储操作失败 |
| `0x1A` | `LT_STATUS_DENIED` | 操作被拒绝 |
| `0x1B` | `LT_STATUS_EXEC_ERROR` | 执行错误 |
| `0x1C` | `LT_STATUS_TOO_LARGE` | 数据超出帧容量 |
| `0x1D` | `LT_STATUS_UNSUPPORTED` | 不支持的操作 |
| `0x1E` | `LT_STATUS_TIMEOUT` | 超时 |
| `0x1F` | `LT_STATUS_CONFLICT` | 冲突（如重复注册） |
| `0x20` | `LT_STATUS_NOT_READY` | 库尚未就绪 |
| `0x21` | `LT_STATUS_INVALID_STATE` | 当前状态不允许此操作 |
| `0x22` | `LT_STATUS_FRAME_DECODE_ERROR` | 帧解码错误 |
| `0x23` | `LT_STATUS_CRC_ERROR` | CRC 校验失败 |
| `0x24` | `LT_STATUS_RX_OVERFLOW` | 接收缓冲区溢出 |
| `0x25` | `LT_STATUS_TX_DROP` | 发送帧被丢弃 |
| `0x7F` | `LT_STATUS_UNKNOWN_ERROR` | 未知错误 |

`0x80-0xFF` 保留给用户自定义状态码。

### 生命周期状态 `lt_state_t`

| 值 | 名称 | 含义 |
|---|---|---|
| `0` | `LT_STATE_UNINIT` | 未初始化 |
| `1` | `LT_STATE_REGISTERING` | 注册阶段 |
| `2` | `LT_STATE_WAIT_DISCOVER` | 等待 Host 连接 |
| `3` | `LT_STATE_CONNECTED` | 已连接，运行时 API 可用 |
| `4` | `LT_STATE_ERROR` | 致命错误 |

### 值类型 `lt_value_type_t`

| 值 | 名称 | 大小 |
|---|---|---|
| `0x01` | `LT_VALUE_BOOL` | 1 字节 |
| `0x02` | `LT_VALUE_U8` | 1 字节 |
| `0x03` | `LT_VALUE_I8` | 1 字节 |
| `0x04` | `LT_VALUE_U16` | 2 字节 |
| `0x05` | `LT_VALUE_I16` | 2 字节 |
| `0x06` | `LT_VALUE_U32` | 4 字节 |
| `0x07` | `LT_VALUE_I32` | 4 字节 |
| `0x08` | `LT_VALUE_U64` | 8 字节 |
| `0x09` | `LT_VALUE_I64` | 8 字节 |
| `0x0A` | `LT_VALUE_F32` | 4 字节 |
| `0x0B` | `LT_VALUE_F64` | 8 字节 |
| `0x0C` | `LT_VALUE_STRING` | 可变（str8 编码） |
| `0x0D` | `LT_VALUE_BYTES` | 可变（bytes8 编码） |
| `0x0E` | `LT_VALUE_ENUM_U8` | 1 字节 |

所有固定长度值在线路中按 little-endian 编码。`STRING` 使用 `u8 len + UTF-8 bytes` 编码，`BYTES` 使用 `u8 len + raw bytes` 编码。

### 日志等级 `lt_log_level_t`

| 值 | 名称 |
|---|---|
| `0x00` | `LT_LOG_LEVEL_DEBUG` |
| `0x01` | `LT_LOG_LEVEL_INFO` |
| `0x02` | `LT_LOG_LEVEL_WARN` |
| `0x03` | `LT_LOG_LEVEL_ERROR` |
| `0x04` | `LT_LOG_LEVEL_FATAL` |

### Feature bitmask

| 宏 | 位 | 说明 |
|---|---|---|
| `LT_FEATURE_LOG_PACKED` | bit 0 | 遥测上报（LOG_REPORT） |
| `LT_FEATURE_PARAM_GET` | bit 1 | 参数读取 |
| `LT_FEATURE_PARAM_SET` | bit 2 | 参数写入 |
| `LT_FEATURE_CMD` | bit 3 | 自定义命令 |
| `LT_FEATURE_LOG_TEXT` | bit 4 | 文本日志 |

连接建立时的协商规则：

```
enabled_features = host_requested_features & mcu_supported_features
```

只有双方都支持的 Feature 才会被启用。`STATUS` 是核心帧，始终可用，不需要 Feature 协商。

### 命令标志

| 宏 | 位 | 说明 |
|---|---|---|
| `LT_CMD_FLAG_HOST_TO_MCU` | bit 0 | 允许 Host 发起此命令 |

### 参数本地策略标志

以下标志仅用于 MCU 本地校验，不会发送给 Host：

| 宏 | 说明 |
|---|---|
| `LT_PARAM_FLAG_READABLE` | 允许读取 |
| `LT_PARAM_FLAG_WRITABLE` | 允许写入 |
| `LT_PARAM_FLAG_HAS_MIN` | 有最小值约束 |
| `LT_PARAM_FLAG_HAS_MAX` | 有最大值约束 |
| `LT_PARAM_FLAG_HAS_DEFAULT` | 有默认值 |
| `LT_PARAM_FLAG_REBOOT_REQUIRED` | 修改后需重启生效 |
| `LT_PARAM_FLAG_USER0` | 用户自定义 |
| `LT_PARAM_FLAG_USER1` | 用户自定义 |

## 5. ID 有效范围

| ID 类型 | 宽度 | 有效范围 | 保留值 |
|---|---|---|---|
| `layout_id` | u8 | `0x01 - 0xFE` | `0x00`, `0xFF` |
| `field_id` | u16 | `0x0001 - 0xFFFE` | `0x0000`, `0xFFFF` |
| `param_id` | u16 | `0x0001 - 0xFFFE` | `0x0000`, `0xFFFF` |
| `cmd_id` | u16 | `0x0001 - 0xFFFE` | `0x0000`, `0xFFFF` |

同一次注册中，同类 ID 必须唯一。
