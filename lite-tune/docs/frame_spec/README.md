# LiteTune v0.5.0 Protocol Specification

**LiteTune = Lightweight Embedded Telemetry, Parameters & Commands Protocol**

**中文名：轻量嵌入式遥测、参数与命令协议**

**协议简写：LiteTune；缩写：`lt`**

当前版本：`v0.5.0`

本目录将 LiteTune 协议拆分为多个 Markdown 模块。每个模块包含对应帧的结构图、字段定义和处理规则。所有文档之间使用相对路径互链。

## 1. 协议心智模型

```text
Host -> MCU: DISCOVER
MCU  -> Host: REGISTER_BEGIN ... REGISTER_END

Host -> MCU: PARAM_SET / PARAM_GET
MCU  -> Host: PARAM_REPORT

Host -> MCU: CMD_REQUEST
MCU  -> Host: CMD_RESPONSE

MCU  -> Host: STATUS(status_code)
MCU  -> Host: LOG_REPORT / LOG_TEXT
```

CMD_REQUEST 和 CMD_RESPONSE 使用独立 Type。

## 2. 单帧原则

每个 RawFrame 必须携带一个完整逻辑消息。

1. 协议不定义跨帧重组。
2. 如果完整数据无法放入协商后的最大 RawFrame，应返回 `TOO_LARGE`、发送 `STATUS`、丢弃该事件，或在本地注册阶段失败。

## 3. 文档索引

| 模块 | 文件 | 内容 |
|---|---|---|
| 总览 | `README.md` | 协议目标、模块拆分、推荐阅读顺序 |
| 公共约定 | [common.md](common.md) | 字节序、基础类型、Feature、Status、Type、ID 分配 |
| 帧层 | [frame.md](frame.md) | WireFrame、RawFrame、FrameID、COBS、CRC、基础收发流程 |
| 初始化与注册 | [init.md](init.md) | DISCOVER、REGISTER_BEGIN、REGISTER_LOG_LAYOUT、REGISTER_PARAM_DESC、REGISTER_CMD_DESC、REGISTER_END |
| 遥测 | [telemetry.md](telemetry.md) | LOG_REPORT，遥测注册 |
| 参数 | [params.md](params.md) | PARAM_SET、PARAM_GET、PARAM_REPORT |
| 命令 | [cmd.md](cmd.md) | CMD_REQUEST、CMD_RESPONSE |
| 运行辅助 | [runtime.md](runtime.md) | STATUS、LOG_TEXT |
| 可靠性 | [reliability.md](reliability.md) | 请求响应匹配、接收检查、帧长度限制 |

## 4. 推荐阅读顺序

```text
README.md
  |
  v
common.md  ---> frame.md
  |              |
  |              v
  +---------> init.md
                 |
                 v
      +----------+----------+
      |          |          |
      v          v          v
telemetry.md  params.md   cmd.md
      |          |          |
      +----------+----------+
                 |
                 v
            runtime.md
                 |
                 v
          reliability.md
```

## 5. 协议边界

LiteTune 负责：

- 数据注册
- 数据传输
- 数据解析
- 请求响应匹配
- 基础校验
- 轻量状态通知

LiteTune 不负责：

- 参数持久化
- Flash 写入
- EEPROM 模拟
- 固件烧录
- 权限认证
- 加密

如果需要保存、加载或恢复参数，建议通过 [CMD](cmd.md) 承载，例如：

```text
name = params.save
name = params.load
name = params.reset_default
```

## 6. 模块关系

```text
+----------------------------------------------------------+
|                     User Application                     |
|  PID / Flight Control / Sensor / UI / Storage / Firmware |
+----------------------+-------------------+---------------+
                       |                   |
                       v                   v
+----------------------+-------------------+---------------+
|                LiteTune Application Layer                |
|       init / telemetry / params / cmd / runtime          |
+----------------------+-------------------+---------------+
                       |
                       v
+----------------------------------------------------------+
|                   LiteTune Frame Layer                   |
|               Magic / Type / FrameID / CRC               |
+----------------------------------------------------------+
|                     COBS Framing                         |
|                 COBS(RawFrame) + 0x00                    |
+----------------------------------------------------------+
|                       Transport                          |
|       UART / USB CDC / Bluetooth SPP / BLE UART          |
+----------------------------------------------------------+
```

## 7. 最小 MCU 实现

```text
common
frame
init:       DISCOVER, REGISTER_BEGIN, REGISTER_LOG_LAYOUT, REGISTER_PARAM_DESC, REGISTER_END
telemetry:  LOG_REPORT packed single
params:     PARAM_SET, PARAM_GET, PARAM_REPORT
runtime:    STATUS
```

## 8. 标准 MCU 实现

```text
最小实现
+ LOG_TEXT
+ CMD
+ REGISTER_CMD_DESC
+ 单帧过大数据的 TOO_LARGE 处理
```
