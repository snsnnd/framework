# 错误码与故障排查

## 1. 错误处理分层

LiteTune 的错误分为两层，使用不同机制返回：

### 协议层错误 → STATUS 帧

帧解码、校验、路由等底层错误，由库自动通过 STATUS 帧通知 Host。详见 [runtime.md](runtime.md)。

### 业务层错误 → 业务响应帧

参数和命令操作中的错误，通过对应的业务响应帧返回：

| 请求 | 错误响应 |
|---|---|
| PARAM_SET | PARAM_REPORT（携带错误状态） |
| PARAM_GET | PARAM_REPORT（携带错误状态） |
| CMD_REQUEST | CMD_RESPONSE（携带错误状态） |

**重要**：业务错误不会用 STATUS 帧替代。如果 Host 发送了一个 PARAM_SET 但参数不存在，MCU 返回的是 PARAM_REPORT（`NOT_FOUND`），而不是 STATUS（`NOT_FOUND`）。

## 2. 请求-响应匹配关系

| 请求类型 | 响应类型 | 匹配字段 |
|---|---|---|
| DISCOVER | REGISTER_BEGIN ... REGISTER_END | 整个注册序列 |
| PARAM_SET | PARAM_REPORT | `request_frame_id` |
| PARAM_GET | PARAM_REPORT | `request_frame_id` |
| CMD_REQUEST | CMD_RESPONSE | `request_frame_id` + `cmd_id` |
| STATUS | 无响应 | — |
| LOG_REPORT | 无响应 | — |
| LOG_TEXT | 无响应 | — |

## 3. 公开 API 返回值速查

### lt_init

| 返回值 | 原因 |
|---|---|
| `OK` | 初始化成功 |
| `BAD_PAYLOAD` | config / send / next_frame_id 为 NULL |

### lt_register_log / lt_register_param / lt_register_cmd

| 返回值 | 原因 |
|---|---|
| `OK` | 注册成功 |
| `INVALID_STATE` | 不在 REGISTERING 状态 |
| `CONFLICT` | 同类注册表已注册 |
| `BAD_PAYLOAD` | 注册表内容无效 |

### lt_register_complete

| 返回值 | 原因 |
|---|---|
| `OK` | 校验通过，进入 WAIT_DISCOVER |
| `INVALID_STATE` | 不在 REGISTERING 状态 |
| `TOO_LARGE` | 某注册记录超出 `LT_RAW_FRAME_SIZE` |
| `BAD_PAYLOAD` | ID 重复、类型无效等 |

### lt_log_report

| 返回值 | 原因 |
|---|---|
| `OK` | 入队成功 |
| `INVALID_STATE` / `NOT_READY` | 未 CONNECTED |
| `NOT_FOUND` | layout_id 未注册 |
| `BAD_PAYLOAD` | 字段指针无效 |
| `TOO_LARGE` | 编码后超出帧限制 |
| `BUSY` / `TX_DROP` | 发送队列已满 |

### lt_log_text

| 返回值 | 原因 |
|---|---|
| `OK` | 入队成功 |
| `INVALID_STATE` | 未 CONNECTED |
| `TOO_LARGE` | 文本过长 |
| `BUSY` | 发送队列已满 |

### lt_rx_from_isr

| 返回值 | 原因 |
|---|---|
| `OK` | 写入 RX ring 成功 |
| `NOT_READY` | 库尚未初始化完成 |
| `BAD_PAYLOAD` | data 为 NULL 但 len > 0 |
| `RX_OVERFLOW` | 缓冲区已满，数据被丢弃 |

## 4. 过大数据处理策略

LiteTune 要求每个逻辑消息完整放入一个帧，不支持跨帧拆分。当数据超出帧大小时：

| 场景 | 处理方式 |
|---|---|
| 注册记录过大 | `lt_register_complete()` 返回 `TOO_LARGE`；连接后若协商帧更小，则发送 STATUS（`TOO_LARGE`） |
| PARAM_GET/SET 响应过大 | 返回 PARAM_REPORT（`ERROR_ONLY` + `TOO_LARGE`，不携带参数值） |
| CMD_RESPONSE 过大 | 返回 CMD_RESPONSE（`TOO_LARGE`，无 user_payload） |
| LOG_REPORT 过大 | `lt_log_report()` 返回 `TOO_LARGE`，不发送 |
| LOG_TEXT 过大 | `lt_log_text()` 返回 `TOO_LARGE`，调用方应拆分 |
| 参数主动事件过大 | 自动拆成多条独立 PARAM_REPORT 事件 |

连接建立时的帧大小协商：

```
peer_max_decoded_frame = min(host_max_decoded_frame, LT_RAW_FRAME_SIZE)
```

如果遇到持续的 `TOO_LARGE` 错误，考虑：
1. 增大 `LT_RAW_FRAME_SIZE`（见 [config.md](config.md)）
2. 减少单个 layout 的字段数
3. 将大型命令响应拆分为多次交互

## 5. 常见故障排查

### Host 连不上 / 卡在 WAIT_DISCOVER

- 确认 UART 波特率和接线正确
- 确认 `lt_rx_from_isr()` 在接收中断中被调用
- 确认主循环中持续调用 `lt_process()`
- 确认 `lt_send_complete()` 在发送完成后被调用
- 用逻辑分析仪或示波器检查线路是否有数据

### 频繁 TX_DROP

发送队列满导致帧被丢弃：
- 降低 `lt_log_report()` / `lt_log_text()` 的调用频率
- 增大 `LT_TX_SLOT_POOL_SIZE` 和 `LT_TX_SEND_QUEUE_SIZE`
- 检查 `lt_send_complete()` 是否被正确调用（未调用会导致发送阻塞）

### 频繁 RX_OVERFLOW

接收缓冲区溢出：
- 增大 `LT_RX_RING_BUFFER_SIZE`
- 确认主循环中 `lt_process()` 调用频率足够高
- 减少主循环中的其他阻塞操作

### 版本不兼容 (VERSION_UNSUPPORTED)

MCU 和 Host 的协议版本不匹配。确认双方使用相同的 LiteTune 协议版本（当前 v0.5.0）。

### 注册时 TOO_LARGE

某个注册记录（如 layout 描述或参数表）的编码长度 + 13 字节帧头超出了 `LT_RAW_FRAME_SIZE`。解决方案：
- 增大 `LT_RAW_FRAME_SIZE`
- 减少单个 layout 的字段数或缩短名称
- 将参数拆分到更少的单次描述中

### CRC_ERROR / FRAME_DECODE_ERROR

传输链路错误：
- 检查 UART 波特率是否匹配
- 检查是否有电磁干扰
- 确认硬件流控配置正确
- 偶发错误属正常现象，库会通过 STATUS 通知 Host
