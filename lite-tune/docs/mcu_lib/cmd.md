# 自定义命令

命令（Commands）允许 Host 调用 MCU 上的自定义操作，如重启、校准、保存参数、触发自检等。MCU 定义命令列表和对应的 callback 函数，库负责将 Host 请求路由到正确的 callback 并返回响应。

需要 `LT_FEATURE_CMD` 在协商中启用。

## 1. 编写命令处理函数

命令 callback 遵循统一的函数签名：

```c
typedef lt_status_t (*lt_cmd_callback_t)(
    const uint8_t *req_payload,   /* Host 发来的请求数据 */
    uint16_t req_len,             /* 请求数据长度 */
    uint8_t *resp_payload,        /* 写入响应数据的缓冲区 */
    uint16_t resp_cap,            /* 响应缓冲区容量 */
    uint16_t *resp_len,           /* 实际写入的响应长度 */
    void *user_ctx                /* 用户上下文指针 */
);
```

### 无返回数据的命令

```c
static lt_status_t cmd_reboot(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    (void)req; (void)req_len;
    (void)resp; (void)resp_cap; (void)ctx;
    *resp_len = 0;          /* 无响应数据 */
    schedule_reboot();
    return LT_STATUS_OK;
}
```

### 带请求和响应数据的命令

```c
static lt_status_t cmd_read_adc(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    if (req_len < 1) return LT_STATUS_BAD_PAYLOAD;

    uint8_t channel = req[0];
    if (channel >= ADC_CHANNEL_COUNT) return LT_STATUS_RANGE_ERROR;

    uint16_t value = adc_read(channel);

    if (resp_cap < 2) return LT_STATUS_TOO_LARGE;
    resp[0] = (uint8_t)(value & 0xFF);
    resp[1] = (uint8_t)(value >> 8);
    *resp_len = 2;

    return LT_STATUS_OK;
}
```

Callback 的返回值会作为 CMD_RESPONSE 中的 `status` 字段发送给 Host。

## 2. 定义命令表并注册

```c
static const lt_cmd_desc_t my_cmds[] = {
    { .cmd_id = 1, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "reboot",   .callback = cmd_reboot,   .user_ctx = NULL },
    { .cmd_id = 2, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "read_adc", .callback = cmd_read_adc, .user_ctx = NULL },
};

static const lt_cmd_registry_t cmd_registry = {
    .cmd_count = 2,
    .cmds = my_cmds,
};

/* 在初始化阶段注册 */
lt_register_cmd(&cmd_registry);
```

注册时库会校验：
- `cmd_id` 在有效范围内且不重复
- `name` 为合法字符串
- `callback` 非空
- `cmd_flags` 中保留位为 0

## 3. 命令执行流程

命令请求和响应由库自动处理：

```
Host ──CMD_REQUEST(cmd_id, user_payload)──> MCU
MCU  查找命令 → 校验 flags → 调用 callback
MCU  ──CMD_RESPONSE(status, user_payload)──> Host
```

**每个 CMD_REQUEST 都会收到一个 CMD_RESPONSE**，无论成功还是失败。

## 4. 命令标志 `cmd_flags`

| 标志 | 说明 |
|---|---|
| `LT_CMD_FLAG_HOST_TO_MCU` (bit 0) | 允许 Host 发起此命令。未设置时 Host 发来的请求会被拒绝（返回 `DENIED`） |
| bit 1-7 | 保留，必须为 0 |

如果需要异步命令、危险操作确认等高级功能，建议在命令的 `user_payload` 中自行定义协议。

## 5. 错误处理

所有错误都通过 CMD_RESPONSE 返回，不使用 STATUS 帧：

| 场景 | CMD_RESPONSE.status |
|---|---|
| 命令不存在 | `NOT_FOUND` |
| 请求 payload 格式错误 | `BAD_PAYLOAD` |
| Host 不允许调用（未设置 `HOST_TO_MCU`） | `DENIED` |
| Callback 返回错误 | callback 的返回值，或 `EXEC_ERROR` |
| 响应数据超出帧大小 | `TOO_LARGE`（无 user_payload） |

## 6. 幂等保护

库会缓存最近一次命令的响应。当 Host 因超时重发相同请求时：

- **相同 FrameID 且请求内容一致**：直接返回缓存的响应，不重复执行 callback
- **相同 FrameID 但请求内容不同**：返回 `CONFLICT`

这是本地保护机制，不等于协议层自动重发。

## 7. 示例：参数持久化命令

LiteTune 核心不处理参数持久化，但你可以通过命令轻松实现：

```c
static lt_status_t cmd_params_save(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    (void)req; (void)req_len;
    (void)resp; (void)resp_cap; (void)ctx;
    *resp_len = 0;
    return flash_save_params() ? LT_STATUS_OK : LT_STATUS_STORAGE_ERROR;
}

static lt_status_t cmd_params_load(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    (void)req; (void)req_len;
    (void)resp; (void)resp_cap; (void)ctx;
    *resp_len = 0;
    return flash_load_params() ? LT_STATUS_OK : LT_STATUS_STORAGE_ERROR;
}

static lt_status_t cmd_params_reset(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    (void)req; (void)req_len;
    (void)resp; (void)resp_cap; (void)ctx;
    *resp_len = 0;
    reset_params_to_default();
    return LT_STATUS_OK;
}

static const lt_cmd_desc_t persistence_cmds[] = {
    { .cmd_id = 100, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "params.save",  .callback = cmd_params_save,  .user_ctx = NULL },
    { .cmd_id = 101, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "params.load",  .callback = cmd_params_load,  .user_ctx = NULL },
    { .cmd_id = 102, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "params.reset", .callback = cmd_params_reset, .user_ctx = NULL },
};
```
