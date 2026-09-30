# 私有 Type 扩展

LiteTune 预留了 `0x40-0x7F` 范围的 Type ID 供项目自定义使用。通过注册扩展 handler，可以在不修改库核心的情况下处理私有帧类型。

大多数项目不需要使用扩展 Type——自定义命令（[cmd.md](cmd.md)）已能覆盖绝大多数需求。扩展 Type 适合高频率、低延迟的私有数据格式。

## 1. Type 范围

| 范围 | 用途 |
|---|---|
| `0x00` | 无效 |
| `0x01-0x3F` | 标准协议 Type |
| **`0x40-0x7F`** | **项目私有扩展** |
| `0x80-0xFF` | 保留，不可使用 |

## 2. 注册扩展 Handler

```c
typedef lt_status_t (*lt_extension_handler_t)(
    uint8_t type,                 /* 收到的 Type ID */
    lt_frame_id_t request_frame_id, /* 帧的 FrameID */
    const uint8_t *payload,       /* 已校验的 payload 数据 */
    uint16_t payload_len,         /* payload 长度 */
    void *user_ctx                /* 用户上下文 */
);
```

Handler 接收的数据已经过完整的帧校验（COBS 解码、Magic 检查、CRC 校验、FrameID 非零检查），只需处理 payload 业务逻辑。

## 3. 使用示例

```c
/* 私有高频传感器数据 */
#define MY_TYPE_SENSOR_STREAM 0x40

static lt_status_t handle_sensor_stream(
    uint8_t type, lt_frame_id_t frame_id,
    const uint8_t *payload, uint16_t payload_len,
    void *ctx)
{
    if (payload_len < 8) return LT_STATUS_BAD_PAYLOAD;

    /* 解析并处理私有数据 */
    process_sensor_data(payload, payload_len);
    return LT_STATUS_OK;
}
```

## 4. 约束

使用扩展 Type 时必须遵守以下规则：

- **帧格式不变**：RawFrame 结构（Magic + Type + FrameID + Payload + CRC16）和 COBS 编码规则保持不变
- **单帧原则不变**：不得要求库进行跨帧重组
- **FrameID 非零**：扩展帧的 FrameID 同样不能为 0
- **不复用标准 Type ID**：不得使用 `0x00-0x3F` 或 `0x80-0xFF` 范围
- **不修改标准语义**：不得改变 PARAM_REPORT、CMD_RESPONSE、STATUS 等标准帧的匹配规则
- **Feature bitmask 独立**：不得改变标准 Feature bit 的含义

## 5. 适用场景

**适合用扩展 Type 的场景**：

- 高频私有数据流（如自定义遥测格式、原始传感器数据）
- 项目私有诊断事件
- 非标准调试协议

**不建议使用扩展 Type，优先用标准功能**：

| 需求 | 推荐方案 |
|---|---|
| 参数保存/加载/恢复 | 自定义命令（[cmd.md](cmd.md)） |
| 文本日志 | `lt_log_text()`（[runtime.md](runtime.md)） |
| 固定字段遥测 | `lt_log_report()`（[telemetry.md](telemetry.md)） |
| 一次性操作请求 | 自定义命令 |
