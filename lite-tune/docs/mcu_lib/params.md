# 远程参数读写

参数（Parameters）允许 Host 远程读取和修改 MCU 上的配置值，如 PID 增益、阈值、使能开关等。MCU 定义参数表并注册后，Host 可通过 PARAM_GET / PARAM_SET 操作参数，MCU 自动响应。

需要 `LT_FEATURE_PARAM_GET` 和/或 `LT_FEATURE_PARAM_SET` 在协商中启用。

## 1. 定义参数表

每个参数通过 `value_ptr` 指向实际变量。Host 读取参数时库自动返回当前值，写入时库自动更新变量：

```c
/* 参数变量 */
static float kp = 1.0f;
static float ki = 0.1f;
static float kd = 0.01f;
static uint8_t motor_enabled = 0;

/* 参数描述 */
static const lt_param_desc_t my_params[] = {
    { .param_id = 1, .value_type = LT_VALUE_F32,
      .name = "kp",  .unit = "",
      .value_ptr = &kp,
      .flags = LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE },

    { .param_id = 2, .value_type = LT_VALUE_F32,
      .name = "ki",  .unit = "",
      .value_ptr = &ki,
      .flags = LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE },

    { .param_id = 3, .value_type = LT_VALUE_F32,
      .name = "kd",  .unit = "",
      .value_ptr = &kd,
      .flags = LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE },

    { .param_id = 4, .value_type = LT_VALUE_BOOL,
      .name = "motor_enabled", .unit = "",
      .value_ptr = &motor_enabled,
      .flags = LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE },
};

static const lt_param_registry_t param_registry = {
    .param_count = 4,
    .params = my_params,
};
```

## 2. 注册

```c
lt_register_param(&param_registry);
```

注册时库会校验：
- `param_id` 在有效范围内且不重复
- `value_type` 有效
- `name` 为合法字符串

## 3. 参数操作流程

注册完成后，参数操作由库自动处理，**无需用户编写额外代码**：

### Host 读取参数（PARAM_GET）

```
Host ──PARAM_GET──> MCU
MCU  ──PARAM_REPORT(当前值)──> Host
```

Host 可以按 ID 读取特定参数，也可以请求读取全部参数。

### Host 写入参数（PARAM_SET）

```
Host ──PARAM_SET(新值)──> MCU
MCU  检查 → 校验 → 写入 value_ptr
MCU  ──PARAM_REPORT(写入后的值)──> Host
```

PARAM_SET 具有**原子性**：如果单次请求包含多个参数，要么全部写入成功，要么全部不写入。库的处理顺序是：

1. 解析全部参数项
2. 校验全部参数项（ID 存在、类型匹配、范围合法、flags 允许写入）
3. 构造响应帧并入队
4. 全部通过后才将新值写入 `value_ptr`

## 4. 本地策略标志

`lt_param_desc_t.flags` 用于 MCU 本地校验，**不会发送给 Host**。Host 只能从注册描述中看到 `param_id`、`value_type`、`name` 和 `unit`。

| 标志 | 效果 |
|---|---|
| `LT_PARAM_FLAG_READABLE` | 允许 PARAM_GET 读取此参数 |
| `LT_PARAM_FLAG_WRITABLE` | 允许 PARAM_SET 写入此参数 |
| `LT_PARAM_FLAG_HAS_MIN` | 启用最小值校验（需本地实现） |
| `LT_PARAM_FLAG_HAS_MAX` | 启用最大值校验（需本地实现） |
| `LT_PARAM_FLAG_HAS_DEFAULT` | 标记有默认值 |
| `LT_PARAM_FLAG_REBOOT_REQUIRED` | 标记修改后需重启生效 |

如果 Host 尝试写入一个不带 `LT_PARAM_FLAG_WRITABLE` 的参数，库会返回 `DENIED`。

## 5. 主动上报参数变化

除了响应 Host 请求外，MCU 也可以主动上报参数变化事件（`PARAM_CHANGED_EVENT`），通知 Host 参数值已被本地修改。此时 `request_frame_id` 为 0，表示非请求触发。

## 6. 错误处理

PARAM_SET / PARAM_GET 的错误始终通过 PARAM_REPORT 返回，不会使用 STATUS 帧：

| 场景 | PARAM_REPORT 状态 |
|---|---|
| 参数不存在 | `NOT_FOUND` |
| 值类型不匹配 | `TYPE_MISMATCH` |
| 值超出范围 | `RANGE_ERROR` |
| 参数不可写 | `DENIED` |
| 响应帧过大 | `TOO_LARGE`（`ERROR_ONLY` 模式，不携带参数值） |

## 7. 数据类型限制

- **固定长度类型**（整数、浮点、bool、enum）：完全支持读写
- **可变长度类型**（`STRING`、`BYTES`）：可以注册和读取，但默认不支持写入。尝试写入可变长度参数会返回 `UNSUPPORTED`

## 8. 参数持久化

LiteTune 核心协议不处理参数的持久化存储。如果需要保存/加载/恢复默认参数，建议通过自定义命令实现。详见 [cmd.md](cmd.md) 中的参数持久化命令示例。
