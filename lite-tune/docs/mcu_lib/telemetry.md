# 遥测数据上报

遥测（Telemetry）用于 MCU 向 Host 周期性发送结构化数据，如传感器读数、状态值等。MCU 定义数据 layout（字段列表），连接后按需调用 `lt_log_report()` 发送当前值。

需要 `LT_FEATURE_LOG_PACKED` 在协商中启用。

## 1. 定义遥测 Layout

每个 layout 是一组字段的集合。通过 `value_ptr` 指向实际变量，`lt_log_report()` 调用时自动读取这些变量的当前值。

```c
/* 要上报的变量 */
static float temperature = 0.0f;
static float humidity = 0.0f;
static uint32_t pressure = 0;

/* 字段描述 */
static const lt_log_field_desc_t env_fields[] = {
    { .field_id = 1, .value_type = LT_VALUE_F32,
      .name = "temperature", .unit = "°C", .value_ptr = &temperature },
    { .field_id = 2, .value_type = LT_VALUE_F32,
      .name = "humidity",    .unit = "%RH", .value_ptr = &humidity },
    { .field_id = 3, .value_type = LT_VALUE_U32,
      .name = "pressure",   .unit = "Pa",  .value_ptr = &pressure },
};

/* Layout 描述 */
static const lt_log_layout_desc_t env_layout = {
    .layout_id = 1,
    .default_period_ms = 200,   /* 建议 Host 显示用的采样周期 */
    .field_count = 3,
    .fields = env_fields,
};
```

可以定义多个 layout（如一个用于电机数据、一个用于环境数据），各自独立上报：

```c
static const lt_log_layout_desc_t layouts[] = {
    env_layout,
    motor_layout,
};

static const lt_log_registry_t log_registry = {
    .layout_count = 2,
    .layouts = layouts,
};
```

## 2. 注册

在 `lt_init()` 之后、`lt_register_complete()` 之前注册：

```c
lt_status_t st = lt_register_log(&log_registry);
if (st != LT_STATUS_OK) {
    /* 处理注册错误 */
}
```

注册时库会校验：
- `layout_id` 在有效范围内且不重复
- 每个 layout 内 `field_id` 不重复
- `value_type` 有效
- `name` 为合法字符串

## 3. 发送遥测报告

在 `CONNECTED` 状态下，调用 `lt_log_report()` 发送一次快照：

```c
/* 先更新数据 */
temperature = read_temp_sensor();
humidity = read_humidity_sensor();
pressure = read_pressure_sensor();

/* 发送 layout 1 的当前值 */
lt_status_t st = lt_log_report(1);
```

典型用法是在定时器回调或主循环中按固定周期调用：

```c
/* 定时器中断（每 200ms 触发） */
void TIM_Callback(void)
{
    temperature = read_temp_sensor();
    humidity = read_humidity_sensor();
    lt_log_report(1);
}
```

每次成功调用后，库会自动递增该 layout 的序列号（`sample_seq`），Host 可据此检测是否有报告丢失。

## 4. 错误处理

| 返回值 | 含义 | 建议 |
|---|---|---|
| `LT_STATUS_OK` | 成功入队 | — |
| `LT_STATUS_INVALID_STATE` | 未处于 CONNECTED 状态 | 等待连接建立 |
| `LT_STATUS_NOT_FOUND` | `layout_id` 未注册 | 检查 ID |
| `LT_STATUS_BAD_PAYLOAD` | 字段指针无效或类型无效 | 检查注册表 |
| `LT_STATUS_TOO_LARGE` | 编码后超出帧大小限制 | 减少字段或增大 `LT_RAW_FRAME_SIZE` |
| `LT_STATUS_BUSY` | 发送队列已满 | 稍后重试或降低上报频率 |

`lt_log_report()` 是尽力发送（best-effort），Host 不会回复确认。如果发送队列满，报告会被丢弃。

## 5. 注意事项

- **数据一致性**：`lt_log_report()` 在调用时读取 `value_ptr` 指向的值。如果数据由 ISR 更新，建议在调用前使用临界区保护，或接受轻微的采样不一致
- **单帧限制**：一个 layout 的所有字段必须能放入一帧。帧头占 13 字节，payload 包含 `layout_id(1) + sample_seq(2) + packed_values`
- **不支持批量**：每次调用发送一个 layout 的一组采样值，不支持在一帧中打包多个采样
