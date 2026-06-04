# EFW Graph 与 Codegen 契约

本文档固定当前阶段的生成边界：EFW 是稳定 C API 底座，Graph 是 Studio 与 codegen 的唯一中间协议，codegen 只把合法 Graph 编译成 EFW application。

## 分层边界

- `EFW`：提供稳定、可手写调用的 C API，不感知 Studio 或 Graph。
- `Graph JSON`：描述 application 拓扑、调度、回调和板级资源，是 Studio/codegen 的共享协议。
- `codegen`：读取 Graph，生成 `application/` 结构、注册 glue、调度 glue 和回调 extern，不推断 UI 意图。
- `Studio`：帮助用户创建合法 Graph、补齐回调、校验和生成，不直接改变 EFW API。
- `custom_files`：用户业务逻辑、自定义算法、任务、模块和事件 publish 调用。
- `board_adapters`：真实 STM32 HAL、ESP-IDF、MSPM0 DriverLib 或自有 BSP glue。

代码中的契约入口是 `tools/codegen/graph/schema.py`，它只做聚合导出。通用 Graph 概念放在 `tools/codegen/graph/common.py`，具体节点契约放在 `tools/codegen/graph/node_contracts.py`。新增节点、修改回调签名、调整生成等级时，必须先更新这些契约模块，再更新 codegen、Studio 模板和文档。

Codegen 的验证入口已拆到 `tools/codegen/validate.py`，渲染/预览/写文件 API 位于 `tools/codegen/generator.py`，`tools/codegen/cli.py` 只负责命令行参数，统一入口是 `tools/efw.py`。

## 生成等级

| 等级 | 含义 |
| ---- | ---- |
| 完整生成 | codegen 生成注册结构、extern、bind 或调度 glue；用户只补回调实现或板级 glue。 |
| 部分生成 | codegen 只生成一部分结构，例如 topic 宏或 subscriber 绑定；业务调用仍由用户代码完成。 |
| 轻量 glue | codegen 生成可编译 wrapper/状态切换 glue；条件、动作和业务逻辑由用户回调实现。 |
| 说明/文档 | 只用于 Studio 组织、说明或代码关系记录，不产生 C 运行代码。 |

## 节点契约

| 节点类型 | 生成等级 | 责任边界 |
| ---- | ---- | ---- |
| `hal.gpio_line_input` | 完整生成 | 生成 mock GPIO 循迹输入 HAL 和板级常量；真实 GPIO/ADC 读取后续放入板级适配。 |
| `hal.custom` | 完整生成 | 生成 HAL 注册 glue；`init/read/write/ioctl` 由 `custom_files` 或 `board_adapters` 实现。 |
| `sensor.line_tracking` | 完整生成 | 绑定 `hal.gpio_line_input`，生成循迹 sensor glue。 |
| `sensor.custom` | 完整生成 | 生成 sensor 注册 glue；`read/init` 回调由用户实现。 |
| `actuator.motor` | 完整生成 | 生成电机 actuator mock write 和 PWM/DIR 常量；真实 PWM/GPIO 写入放入板级适配。 |
| `actuator.custom` | 完整生成 | 生成 actuator 注册 glue；`write/init/enable/disable` 回调由用户实现。 |
| `algorithm.pid` | 完整生成 | 使用 EFW 内置 PID，生成 PID ctx 和 algorithm 注册。 |
| `algorithm.custom` | 完整生成 | 生成 algorithm 注册 glue；`run` 回调由用户实现；接入 LineFollower 时必须声明 `io_contract=efw_pid`。 |
| `processor.custom` | 部分生成 | 生成数据契约 wrapper；位于 `Sensor → Processor → Algorithm/Actuator` edge 链上时自动纳入周期数据流调度；`process(ctx, in, out)` 由用户实现。 |
| `module.custom` | 完整生成 | 生成 module 注册和 lifecycle 调用；模块行为由用户回调实现。 |
| `task.periodic` | 完整生成 | 生成 tick scheduler 调用；`period_ms` 必须是 `project.tick_ms` 整数倍。 |
| `project.module` | 说明/文档 | 当前只表示 Studio 页面、分组和归属，不是独立编译单元。 |
| `event.topic` | 部分生成 | 生成 `APP_TOPIC_*` 宏。 |
| `event.publisher` | 说明/文档 | 表达发布意图；实际 `efw_topic_publish()` 写在用户任务或模块代码中。 |
| `event.subscriber` | 部分生成 | 生成 `efw_topic_subscribe()` 绑定；topic callback 由用户实现。 |
| `state.machine` | 轻量 glue | 生成轻量状态机 runner，不是完整状态机引擎。 |
| `state.state` | 轻量 glue | 生成状态 entry；`on_enter/on_update/on_exit` 由用户实现。 |
| `state.transition` | 轻量 glue | 生成条件转换 glue；`condition` 必填，`event_trigger` 当前只作为注释/语义标记。 |
| `custom.card` | 说明/文档 | 纯说明卡片，不产生 C 输出。 |
| `custom.code` | 说明/文档 | 描述代码实现关系；源码内容仍保存在 `custom_files` 或 `board_adapters`。 |

## 回调签名

| 场景 | 签名 |
| ---- | ---- |
| HAL init | `efw_status_t fn(void *ctx)` |
| HAL read | `efw_status_t fn(void *ctx, void *buf, uint16_t len, uint16_t *actual)` |
| HAL write | `efw_status_t fn(void *ctx, const void *buf, uint16_t len, uint16_t *actual)` |
| HAL ioctl | `efw_status_t fn(void *ctx, uint32_t cmd, void *arg)` |
| Sensor init | `efw_status_t fn(void *ctx)` |
| Sensor read | `efw_status_t fn(void *ctx, void *out)` |
| Actuator write | `efw_status_t fn(void *ctx, const void *cmd)` |
| Algorithm run | `efw_status_t fn(void *ctx, const void *in, void *out)` |
| Processor process | `efw_status_t fn(void *ctx, const void *in, void *out)` |
| Module lifecycle | `efw_status_t fn(void *ctx)` |
| Periodic task | `efw_status_t fn(void)` |
| Topic subscriber | `void fn(uint16_t topic_id, const void *data, uint16_t size, void *user)` |
| Condition | `int fn(void)`、`uint8_t fn(void)` 或 `bool fn(void)` |

## 文件保护规则

- 生成文件清单由 `graph_schema.GENERATED_FILES` 固定。
- `custom_files` 和 `board_adapters` 不能覆盖生成文件。
- 输出目录非空时 CLI 必须传 `--force`，UI 必须确认覆盖。
- 覆盖已有生成文件前会备份到 `.efw_backup/`。
- 不属于本次生成清单的用户文件会保留，不会删除。

## 变更规则

1. 需要新增节点时，先在 `graph_schema.NODE_CONTRACTS` 定义生成等级、必填字段、回调和边界。
2. 再补 codegen 的校验和渲染逻辑。
3. 再补 Studio 模板、属性选择、端口语义和卡片摘要。
4. 最后更新示例 Graph 和本文档。

当前阶段不让 EFW 追随 UI 频繁变化。只有多个生成场景暴露出同一个底层缺口时，才小步补充 EFW API。

## 数据契约与运行管线

- 顶层可选 `contracts[]`、`project.module.inputs/outputs`、`processor.custom.input_contract/output_contract` 会被合并为 contract registry，并生成 `APP_CONTRACT_*` 宏。
- Contract 可以声明 `c_type`、`size`、`align`；自动 dataflow 要求参与传递的 contract 有确定 `size`，生成器会用最大 contract size 决定 `APP_DATAFLOW_BUFFER_SIZE`。内置 contract 包括 `efw_line_tracking_data_t`、`efw_pid_input_t`、`efw_pid_output_t`、`efw_motor_cmd_t` 和常见标量。内置 size 是 codegen 元数据，必须与 C 头文件 ABI 同步；生成的 `app_bootstrap.c` 会包含 `sizeof(c_type)` 编译期检查，`efw_contract_sizes` 主机侧测试也会校验内置 contract 的 `sizeof`/对齐，防止结构体 padding/ABI 变化后继续生成错误缓冲区。
- `project.module` 仍是 Studio 页面/系统结构节点，不生成独立编译单元；强类型接口生成留给后续模块编译阶段。
- `data_flow` / `control_flow` edge 如果组成 contract 兼容的 `Sensor → Processor/Algorithm → Actuator` 路径，codegen 会生成 `app_dataflow_<path>()` 并在 `app_update_1ms()` 中按周期执行。
- `algorithm.pid` 的输入 contract 固定为 `efw_pid_input_t`，输出固定为 `efw_pid_output_t`；不允许普通 sensor 数据绕过 processor 直接进入 PID 自动管线。
- 已属于 `control.line_follower` flow 的 sensor/pid/motor 默认会从普通自动 dataflow 中排除，避免双重调度。`app_update_1ms()` 的生成顺序固定为 dataflow pipelines、line_follower flows、task.periodic、state-machine ticks、module poll_all。
- `processor.custom → project.module` 这类跨层连接只声明接口契约，不表示 processor 调用模块。
