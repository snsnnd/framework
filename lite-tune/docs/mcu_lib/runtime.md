# 状态通知与文本日志

Runtime 模块提供两种辅助通信机制：STATUS 状态通知和 LOG_TEXT 文本日志。

## 1. STATUS 状态通知

STATUS 是库自动发送的异步通知帧，用于向 Host 报告协议层错误和运行状况。**用户通常不需要直接与 STATUS 交互**——库会在适当时机自动发送。

### 何时自动发送

| 事件 | STATUS 码 |
|---|---|
| 收到帧 COBS 解码失败 | `FRAME_DECODE_ERROR` |
| 帧头格式错误（过短、Magic 错误） | `FRAME_DECODE_ERROR` |
| CRC 校验失败 | `CRC_ERROR` |
| 未知帧类型 | `UNKNOWN_TYPE` |
| FrameID 为 0 | `BAD_PAYLOAD` |
| DISCOVER 协议版本不兼容 | `VERSION_UNSUPPORTED` |
| 注册记录超出协商帧大小 | `TOO_LARGE` |
| 发送队列已满导致丢帧 | `TX_DROP` |
| 接收缓冲区溢出 | `RX_OVERFLOW` |
| 库尚未就绪时收到帧 | `NOT_READY` |

### STATUS 的特点

- **异步通知**：STATUS 不是对某个请求的响应，Host 不应将其与 pending request 匹配
- **尽力发送**：如果发送队列已满，STATUS 本身也会被丢弃
- **自动限流**：库会合并重复的 STATUS，避免高频错误导致的帧风暴
- **不替代业务响应**：参数操作错误用 PARAM_REPORT 返回，命令错误用 CMD_RESPONSE 返回，不会用 STATUS 替代

## 2. 文本日志 LOG_TEXT

`lt_log_text()` 用于从 MCU 向 Host 发送自由格式的文本消息，适合调试信息、事件通知等场景。

需要 `LT_FEATURE_LOG_TEXT` 在协商中启用。

### 基本用法

```c
lt_log_text(LT_LOG_LEVEL_INFO,  "System started");
lt_log_text(LT_LOG_LEVEL_WARN,  "Battery low: 3.2V");
lt_log_text(LT_LOG_LEVEL_ERROR, "Sensor timeout on I2C1");
```

### 日志等级

| 等级 | 宏 | 用途 |
|---|---|---|
| 0 | `LT_LOG_LEVEL_DEBUG` | 调试细节 |
| 1 | `LT_LOG_LEVEL_INFO` | 一般信息 |
| 2 | `LT_LOG_LEVEL_WARN` | 警告 |
| 3 | `LT_LOG_LEVEL_ERROR` | 错误 |
| 4 | `LT_LOG_LEVEL_FATAL` | 致命错误 |

Host 端工具可根据等级过滤显示。

### 使用条件

- 必须在 `CONNECTED` 状态下调用
- `LT_FEATURE_LOG_TEXT` 必须在协商中启用
- 文本必须是 UTF-8 编码，最长 **255 字节**（不含 C 字符串的 `\0`）

### 返回值

| 返回值 | 含义 | 建议 |
|---|---|---|
| `LT_STATUS_OK` | 成功入队 | — |
| `LT_STATUS_INVALID_STATE` | 未处于 CONNECTED 状态 | 等待连接 |
| `LT_STATUS_TOO_LARGE` | 文本加帧头超出帧大小限制 | 拆分为多条短消息 |
| `LT_STATUS_BUSY` | 发送队列已满 | 稍后重试或降低频率 |

### 注意事项

- LOG_TEXT 是尽力发送，Host 不会回复确认
- 长文本需要调用方自行拆分为多条 `lt_log_text()` 调用
- **高频固定格式数据应使用 `lt_log_report()`**，LOG_TEXT 适合低频事件性消息
- 格式化字符串需先由应用层完成（如 `snprintf`），库不提供 printf 风格的接口

### 格式化示例

```c
char buf[128];
snprintf(buf, sizeof(buf), "ADC ch%d = %d mV", channel, mv);
lt_log_text(LT_LOG_LEVEL_DEBUG, buf);
```
