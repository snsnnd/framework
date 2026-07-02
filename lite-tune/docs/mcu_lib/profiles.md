# Profile 选择

LiteTune MCU Library 提供两种预设 Profile，适用于不同资源和功能需求的 MCU。Profile 通过 `lt_config_t.mcu_supported_features` 声明，在 DISCOVER 时与 Host 协商。

## 1. Profile 对比

| | 最小 Profile | 标准 Profile |
|---|---|---|
| **适用场景** | 资源极小的 MCU，仅需遥测和参数 | 通用 MCU，需要完整功能 |
| **遥测** | ✅ LOG_REPORT | ✅ LOG_REPORT |
| **参数读取** | ✅ PARAM_GET | ✅ PARAM_GET |
| **参数写入** | ✅ PARAM_SET | ✅ PARAM_SET |
| **自定义命令** | ❌ | ✅ CMD_REQUEST / CMD_RESPONSE |
| **文本日志** | ❌ | ✅ LOG_TEXT |
| **STATUS 通知** | ✅ 始终可用 | ✅ 始终可用 |

## 2. 最小 Profile

最小 Profile 适合仅需要数据上报和参数调节的场景，不注册命令表，不使用文本日志。

```c
lt_config_t cfg = {
    .send = my_send,
    .next_frame_id = my_next_id,
    .device_name = "Sensor",
    .mcu_supported_features = LT_FEATURE_LOG_PACKED
                            | LT_FEATURE_PARAM_GET
                            | LT_FEATURE_PARAM_SET,
};

lt_init(&cfg);
lt_register_log(&log_registry);
lt_register_param(&param_registry);
/* 不调用 lt_register_cmd() */
lt_register_complete();
```

当 Host 发送不支持的请求类型（如 CMD_REQUEST）时，MCU 会自动返回 `UNSUPPORTED`。

## 3. 标准 Profile

标准 Profile 启用全部功能：

```c
lt_config_t cfg = {
    .send = my_send,
    .next_frame_id = my_next_id,
    .device_name = "MotorCtrl",
    .mcu_supported_features = LT_FEATURE_LOG_PACKED
                            | LT_FEATURE_PARAM_GET
                            | LT_FEATURE_PARAM_SET
                            | LT_FEATURE_CMD
                            | LT_FEATURE_LOG_TEXT,
};

lt_init(&cfg);
lt_register_log(&log_registry);
lt_register_param(&param_registry);
lt_register_cmd(&cmd_registry);
lt_register_complete();
```

## 4. 自定义组合

不必完全遵循上述两种 Profile，可以按需组合。例如只需要命令而不需要参数写入：

```c
.mcu_supported_features = LT_FEATURE_LOG_PACKED
                        | LT_FEATURE_PARAM_GET
                        | LT_FEATURE_CMD,
```

协商规则：

```
enabled_features = host_requested_features & mcu_supported_features
```

只有双方都支持的 Feature 才会启用。MCU 不应在 `mcu_supported_features` 中声明未实际实现的能力。

## 5. 不属于核心协议的能力

以下能力不通过 Feature bitmask 协商，需要在应用层自行实现：

- 参数持久化（通过自定义命令，见 [cmd.md](cmd.md)）
- 权限认证
- 数据加密
- 固件烧录 / OTA
- 跨帧大数据传输
- 协议层自动重发

如需要这些功能，可通过自定义命令的 `user_payload` 承载，或使用私有 Type 扩展（见 [extensions.md](extensions.md)）。
