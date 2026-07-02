# LiteTune MCU Library

LiteTune MCU Library 是一个 header-only C 库，用于在 MCU 上实现 LiteTune v0.5.0 协议。它提供遥测上报、远程参数读写和自定义命令三大核心能力，通过 UART / USB CDC / BLE 等串行通道与宿主机通信。

## 特性

- **Header-only**：无需独立编译库文件，只需在一个翻译单元中定义 `LITETUNE_IMPLEMENTATION` 即可集成
- **零动态内存分配**：所有缓冲区静态分配，适合资源受限 MCU
- **ISR 安全**：接收入口 `lt_rx_from_isr()` 可直接在中断中调用
- **可裁剪**：通过 Feature bitmask 协商，按需启用遥测、参数、命令和文本日志

## 快速开始

### 第 1 步：创建平台配置文件

```c
/* lt_user_config.h */
#define LT_RAW_FRAME_SIZE    256u
#define LT_CRITICAL_ENTER()  __disable_irq()
#define LT_CRITICAL_EXIT()   __enable_irq()
```

### 第 2 步：在一个翻译单元中包含实现

```c
/* litetune_impl.c — 整个项目只需要这一个文件 */
#include "lt_user_config.h"
#define LITETUNE_IMPLEMENTATION
#include "litetune.h"
```

### 第 3 步：在其他文件中正常使用

```c
/* app.c */
#include "lt_user_config.h"
#include "litetune.h"

/* 直接调用 lt_* API */
```

## 完整集成示例

以下展示一个最小可运行的集成模板：

```c
#include "lt_user_config.h"
#define LITETUNE_IMPLEMENTATION
#include "litetune.h"

/* ---------- 平台回调 ---------- */

static lt_status_t my_send(const void *data, uint16_t len)
{
    /* 启动 UART DMA 发送，成功返回 LT_STATUS_OK */
    return uart_dma_send(data, len);
}

static lt_frame_id_t my_next_frame_id(void)
{
    static lt_frame_id_t id = 1;
    return id++;
}

/* ---------- 遥测 layout ---------- */

static float temperature = 0.0f;
static uint16_t rpm = 0;

static const lt_log_field_desc_t motor_fields[] = {
    { .field_id = 1, .value_type = LT_VALUE_F32,  .name = "temperature",
      .unit = "°C", .value_ptr = &temperature },
    { .field_id = 2, .value_type = LT_VALUE_U16, .name = "rpm",
      .unit = "RPM", .value_ptr = &rpm },
};

static const lt_log_layout_desc_t motor_layout = {
    .layout_id = 1,
    .default_period_ms = 100,
    .field_count = 2,
    .fields = motor_fields,
};

static const lt_log_registry_t log_registry = {
    .layout_count = 1,
    .layouts = &motor_layout,
};

/* ---------- 参数 ---------- */

static float kp = 1.0f;

static const lt_param_desc_t my_params[] = {
    { .param_id = 1, .value_type = LT_VALUE_F32, .name = "kp",
      .unit = "", .value_ptr = &kp, .flags = LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE },
};

static const lt_param_registry_t param_registry = {
    .param_count = 1,
    .params = my_params,
};

/* ---------- 命令 ---------- */

static lt_status_t cmd_reboot(
    const uint8_t *req, uint16_t req_len,
    uint8_t *resp, uint16_t resp_cap, uint16_t *resp_len,
    void *ctx)
{
    (void)req; (void)req_len; (void)resp; (void)resp_cap; (void)ctx;
    *resp_len = 0;
    /* 实际重启逻辑 */
    return LT_STATUS_OK;
}

static const lt_cmd_desc_t my_cmds[] = {
    { .cmd_id = 1, .cmd_flags = LT_CMD_FLAG_HOST_TO_MCU,
      .name = "reboot", .callback = cmd_reboot, .user_ctx = NULL },
};

static const lt_cmd_registry_t cmd_registry = {
    .cmd_count = 1,
    .cmds = my_cmds,
};

/* ---------- 主函数 ---------- */

int main(void)
{
    hw_init();

    /* 1. 初始化 */
    lt_config_t cfg = {
        .send = my_send,
        .next_frame_id = my_next_frame_id,
        .device_name = "MotorCtrl",
        .mcu_supported_features = LT_FEATURE_LOG_PACKED
                                | LT_FEATURE_PARAM_GET
                                | LT_FEATURE_PARAM_SET
                                | LT_FEATURE_CMD
                                | LT_FEATURE_LOG_TEXT,
    };
    lt_init(&cfg);

    /* 2. 注册 */
    lt_register_log(&log_registry);
    lt_register_param(&param_registry);
    lt_register_cmd(&cmd_registry);
    lt_register_complete();

    /* 3. 主循环 */
    while (1) {
        lt_process();               /* 驱动收发 */

        temperature = read_temp();  /* 更新遥测数据 */
        rpm = read_rpm();
        lt_log_report(1);           /* 上报 layout 1 */

        app_tasks();
    }
}

/* ---------- 中断回调 ---------- */

/* UART 接收中断 */
void UART_RxCallback(const uint8_t *data, uint16_t len)
{
    lt_rx_from_isr(data, len);
}

/* UART DMA 发送完成中断 */
void UART_TxDoneCallback(void)
{
    lt_send_complete();
}
```

## 生命周期

库经历以下状态：

```
UNINIT ──lt_init()──> REGISTERING ──lt_register_complete()──> WAIT_DISCOVER
                                                                    │
                                              Host 发送 DISCOVER ───┘
                                                                    v
                                                               CONNECTED
```

| 状态 | 允许的操作 |
|---|---|
| `UNINIT` | 调用 `lt_init()` |
| `REGISTERING` | 调用 `lt_register_log/param/cmd()`，最后调用 `lt_register_complete()` |
| `WAIT_DISCOVER` | 等待 Host 连接；`lt_process()` 开始处理收发 |
| `CONNECTED` | 所有运行时 API 可用：`lt_log_report()`、`lt_log_text()` 等 |

收到新的 DISCOVER 时，库自动重新发送注册信息并回到 CONNECTED 状态。

## 文档导航

| 文档 | 内容 |
|---|---|
| [config.md](config.md) | 配置宏、平台移植 |
| [api-reference.md](api-reference.md) | 公开类型与函数完整参考 |
| [telemetry.md](telemetry.md) | 遥测数据上报 |
| [params.md](params.md) | 远程参数读写 |
| [cmd.md](cmd.md) | 自定义命令 |
| [runtime.md](runtime.md) | 状态通知与文本日志 |
| [error-handling.md](error-handling.md) | 错误码与故障排查 |
| [profiles.md](profiles.md) | 最小 / 标准 Profile 选择 |
| [extensions.md](extensions.md) | 私有 Type 扩展 |

## 协议规范

帧格式、Payload 布局等协议细节请参考 [LiteTune v0.5.0 协议规范](../frame_spec/README.md)。
