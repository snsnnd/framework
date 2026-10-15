# 配置与平台移植

LiteTune MCU Library 通过预处理宏进行配置。所有宏必须在 `#include "litetune.h"` 之前定义，且所有翻译单元使用相同的配置值。

推荐做法：创建一个 `lt_user_config.h`，在所有源文件中首先包含它。

```c
/* lt_user_config.h */
#include "lt_user_config.h"
#include "litetune.h"
```

## 1. 平台回调（必须提供）

### 临界区保护

必须提供临界区宏，用于保护 ISR 与主循环之间的共享数据（RX ring、TX 队列状态等）：

```c
#define LT_CRITICAL_ENTER()  /* 进入临界区 */
#define LT_CRITICAL_EXIT()   /* 退出临界区 */
```

常见平台示例：

```c
/* STM32 裸机 */
#define LT_CRITICAL_ENTER()  __disable_irq()
#define LT_CRITICAL_EXIT()   __enable_irq()

/* FreeRTOS */
#define LT_CRITICAL_ENTER()  taskENTER_CRITICAL()
#define LT_CRITICAL_EXIT()   taskEXIT_CRITICAL()

/* 单核无中断竞争场景（需明确确认安全） */
#define LT_CRITICAL_ENTER()  do {} while (0)
#define LT_CRITICAL_EXIT()   do {} while (0)
```

### 发送回调与 FrameID 生成

在 `lt_config_t` 中提供（见 [api-reference.md](api-reference.md)）：

```c
lt_config_t cfg = {
    .send = my_uart_send,        /* 底层发送函数 */
    .next_frame_id = my_next_id, /* FrameID 生成函数 */
    .device_name = "MyDevice",
    .mcu_supported_features = LT_FEATURE_LOG_PACKED | LT_FEATURE_PARAM_GET | ...,
};
```

## 2. 容量宏参考

所有容量宏都有默认值，仅在需要调整时才覆盖定义。

### 帧大小

| 宏 | 默认值 | 说明 |
|---|---|---|
| `LT_RAW_FRAME_SIZE` | `256` | MCU 可处理的最大 RawFrame 字节数。这也是 DISCOVER 协商时 MCU 报告的 `mcu_max_decoded_frame` |
| `LT_WIRE_FRAME_SIZE` | 自动计算 | COBS 编码后的最大长度，无需手动设置 |

`LT_RAW_FRAME_SIZE` 决定了单帧能承载的最大 Payload。增大此值可支持更多参数或更长命令数据，但会增加内存占用。最小值为 `24`。

### 接收缓冲

| 宏 | 默认值 | 说明 |
|---|---|---|
| `LT_RX_RING_BUFFER_SIZE` | `4 × LT_WIRE_FRAME_SIZE` | RX 环形缓冲区大小。ISR 写入、主循环读取 |
| `LT_RX_MAX_FRAMES_PER_PROCESS` | `4` | 每次 `lt_process()` 最多处理的接收帧数，防止长时间阻塞主循环 |

### 发送缓冲

| 宏 | 默认值 | 说明 |
|---|---|---|
| `LT_TX_SLOT_POOL_SIZE` | `16` | 发送槽池大小，决定最多同时排队的待发送帧数 |
| `LT_TX_SEND_QUEUE_SIZE` | `8` | FIFO 发送队列深度 |
| `LT_TX_SENDING_FRAME_COUNT` | `4` | 单次批量发送的最大帧数 |
| `LT_TX_SENDING_BUFFER_SIZE` | `LT_TX_SENDING_FRAME_COUNT × LT_WIRE_FRAME_SIZE` | 批量发送缓冲区大小 |

### 参数与命令

| 宏 | 默认值 | 说明 |
|---|---|---|
| `LT_PARAM_SET_MAX_ITEMS` | `8` | PARAM_SET 单次请求最多可包含的参数项数 |
| `LT_PARAM_MAX_VALUE_SIZE` | `16` | 单个参数值的最大字节数 |
| `LT_CMD_RESPONSE_BUFFER_SIZE` | `64` | 命令响应 user payload 的缓冲区大小 |
| `LT_CMD_RESPONSE_CACHE_SIZE` | 同上 | 命令幂等缓存的大小 |

### 运行时

| 宏 | 默认值 | 说明 |
|---|---|---|
| `LT_STATUS_MIN_INTERVAL_MS` | `100` | 连续相同 STATUS 帧的最小发送间隔（限流） |

## 3. Header-only 集成模式

LiteTune 采用 stb-style header-only 模式：

### 标准模式（推荐）

在**一个且仅一个**翻译单元中定义 `LITETUNE_IMPLEMENTATION`：

```c
/* litetune_impl.c */
#include "lt_user_config.h"
#define LITETUNE_IMPLEMENTATION
#include "litetune.h"
```

其他翻译单元只需包含头文件（获得声明）：

```c
/* other.c */
#include "lt_user_config.h"
#include "litetune.h"
```

### 单文件模式（仅限简单项目）

如果整个项目只有一个翻译单元使用 LiteTune，可以使用 `LITETUNE_STATIC`：

```c
#define LITETUNE_STATIC
#define LITETUNE_IMPLEMENTATION
#include "litetune.h"
```

此模式下所有函数为 `static`，仅在当前翻译单元可见。

## 4. 配置一致性

所有翻译单元必须使用相同的配置宏值。如果不同文件使用不同的 `LT_RAW_FRAME_SIZE` 等宏，库的声明和实现对缓冲区大小的理解将不一致，导致未定义行为。

**正确做法**：统一使用 `lt_user_config.h`。

## 5. 帧大小与协议协商

`LT_RAW_FRAME_SIZE` 不仅是本地缓冲区大小，也参与连接建立时的帧大小协商：

```
peer_max_decoded_frame = min(host_max_decoded_frame, LT_RAW_FRAME_SIZE)
```

协商后，双方发送的帧都不会超过 `peer_max_decoded_frame`。如果遥测 layout 或参数表过大无法放入协商后的帧，库会返回 `LT_STATUS_TOO_LARGE`。

确定 `LT_RAW_FRAME_SIZE` 时需考虑：
- 最大遥测 layout 的编码长度 + 13 字节帧头
- 全部参数描述的编码长度 + 13 字节帧头
- 命令响应的最大 payload + 帧头

详见 [error-handling.md](error-handling.md) 中的过大数据处理策略。
