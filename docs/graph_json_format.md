# EFW Graph JSON 格式协议

本文档说明用户如何手写 EFW Graph JSON。Graph JSON 是 Studio、codegen 和 project workflow 共享的应用描述格式：它描述项目元数据、节点、连线、数据契约、调度、事件、状态机、自定义代码和板级适配。生成器只接受通过校验的 Graph。

开发者级生成边界见 `docs/graph_contract.md`。本文面向使用者，重点是“JSON 怎么写”。

## 最小结构

一个 Graph 根节点必须是 JSON object，至少包含 `project` 和非空 `nodes`。

```json
{
  "project": {
    "name": "my_app",
    "tick_ms": 1
  },
  "board": {
    "profile": "stm32-basic",
    "pin_plan": []
  },
  "nodes": [
    {
      "id": "system_core",
      "type": "project.module",
      "display_name": "System Core"
    }
  ],
  "edges": [],
  "flows": [],
  "tasks": [],
  "contracts": [],
  "custom_files": [],
  "board_adapters": []
}
```

推荐始终写出这些顶层字段，即使数组为空，方便后续维护。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| ---- | ---- | ---- | ---- |
| `project` | object | 是 | 项目元数据。 |
| `board` | object | 否 | 板级 profile 和引脚规划。未写时按空对象处理。 |
| `nodes` | array | 是 | 节点列表，不能为空。每个节点必须有唯一 `id` 和有效 `type`。 |
| `edges` | array | 否 | 节点连线。空图可写 `[]`。 |
| `flows` | array | 否 | 高层控制 flow，目前支持 `control.line_follower`。 |
| `tasks` | array | 否 | 周期任务。也可以用 `task.periodic` 节点表达。 |
| `contracts` | array | 否 | 自定义数据契约声明。 |
| `custom_files` | array | 否 | 用户业务 C 源码/头文件，会写入生成 application。 |
| `board_adapters` | array | 否 | 板级适配 C 源码/头文件，适合放 STM32 HAL/BSP glue。 |
| `ui` | object | 否 | Studio 布局数据。手写 Graph 可以忽略。 |

## project

```json
"project": {
  "name": "generated_generic_embedded_app",
  "tick_ms": 1,
  "dataflow_buffer_size": 64,
  "auto_dataflow_include_line_follower": false
}
```

| 字段 | 类型 | 默认 | 说明 |
| ---- | ---- | ---- | ---- |
| `name` | string | `generated_app` | 项目名，也会影响生成目录/符号说明。 |
| `tick_ms` | integer | `1` | 主循环 tick 基准，必须大于 0。所有 `period_ms` 必须是它的整数倍。 |
| `dataflow_buffer_size` | integer | 自动 | 自动 dataflow 缓冲区下限。最终值会取该值、64、最大 contract size 的最大值。 |
| `auto_dataflow_include_line_follower` | bool | `false` | 默认不把已属于 line follower flow 的节点再纳入普通自动 dataflow，避免重复调度。 |

## board

```json
"board": {
  "profile": "stm32-basic",
  "pin_plan": [
    { "node": "left_motor", "usage": "pwm", "port": "A", "pin": 8, "channel": 1 }
  ]
}
```

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `profile` | string | 板级 profile 名称，例如 `stm32-basic` 或项目数据目录中的 profile。 |
| `pin_plan` | array | 可选引脚规划。每项至少应有 `node`，可附带 `usage`、`port`、`pin`、`channel`。 |

## nodes

节点是 Graph 的核心。每个节点必须是 object，并且至少包含：

```json
{ "id": "unique_node_id", "type": "node.type" }
```

规则：

- `id` 必须是非空字符串，并且在 `nodes[]` 中唯一。
- `type` 必须是受支持的节点类型。
- 如果节点有 `module` 字段，它必须引用一个已存在的 `project.module` 节点。
- 回调字段如 `read`、`write`、`process`、`run`、`poll`、`callback` 必须是有效 C 标识符，并且函数实现必须出现在 `custom_files` 或 `board_adapters` 中。

### 支持的节点类型

| 类型 | 用途 |
| ---- | ---- |
| `project.module` | 模块/子系统分组，也会生成轻量 module shell。 |
| `hal.gpio_line_input` | 多路 GPIO/比较器循迹输入 HAL。 |
| `hal.custom` | 自定义 HAL，用户实现 init/read/write/ioctl 中至少一个。 |
| `sensor.line_tracking` | 循迹传感器，绑定 `hal.gpio_line_input`。 |
| `sensor.custom` | 自定义传感器，用户实现 `read`。 |
| `actuator.motor` | 内置电机执行器，真实写入由 board adapter 实现。 |
| `actuator.custom` | 自定义执行器，用户实现 `write`。 |
| `algorithm.pid` | 内置 PID。 |
| `algorithm.custom` | 自定义算法，用户实现 `run`。 |
| `processor.custom` | 自定义数据处理/契约转换节点，用户实现 `process` 或使用字段映射。 |
| `module.custom` | 自定义模块，用户实现 lifecycle/poll。 |
| `task.periodic` | 周期任务节点。 |
| `event.topic` | 事件 topic 定义，生成 `APP_TOPIC_*`。 |
| `event.publisher` | 发布者说明/发布 wrapper。 |
| `event.subscriber` | 订阅者，生成 `efw_topic_subscribe()` 绑定。 |
| `state.machine` | 轻量状态机容器。 |
| `state.state` | 状态机状态。 |
| `state.transition` | 状态转换。 |
| `data.enum` | 文档型 enum 声明，C enum 仍由用户代码定义。 |
| `data.struct` | 文档型 struct 声明，可用于字段映射校验。C struct 仍由用户代码定义。 |
| `custom.card` | 纯说明卡片，不生成 C。 |
| `custom.interface_card` | Studio 接口摘要卡片，不生成 C。 |
| `custom.code` | 代码关系说明，源码正文放在 `custom_files`/`board_adapters`。 |

## 常用节点写法

### project.module

```json
{
  "id": "motion_module",
  "type": "project.module",
  "display_name": "Motion",
  "description": "电机和运动控制",
  "inputs": [],
  "outputs": []
}
```

`inputs` 和 `outputs` 如果填写，里面的名字必须能在 contract registry 中找到。也就是说要么是内置 contract，要么在顶层 `contracts[]` 声明。

### hal.custom

```json
{
  "id": "uart_debug",
  "type": "hal.custom",
  "hal_type": "uart",
  "bus_id": 1,
  "ctx": "0",
  "init": "app_uart_debug_init",
  "write": "app_uart_debug_write",
  "module": "system_core"
}
```

`hal.custom` 至少需要 `init`、`read`、`write`、`ioctl` 中的一个。常用回调签名：

```c
efw_status_t app_uart_debug_init(void *ctx);
efw_status_t app_uart_debug_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual);
```

### sensor.custom

```json
{
  "id": "battery_sensor",
  "type": "sensor.custom",
  "sensor_type": "custom",
  "channel_count": 1,
  "hal_name": "uart_debug",
  "ctx": "0",
  "read": "app_battery_sensor_read",
  "output_contract": "float",
  "output_type": "float",
  "module": "system_core"
}
```

`hal_name` 如果填写，必须引用一个 `hal.*` 节点。`read` 签名：

```c
efw_status_t app_battery_sensor_read(void *ctx, void *out, uint16_t out_size);
```

### actuator.custom

```json
{
  "id": "status_led",
  "type": "actuator.custom",
  "actuator_type": "led",
  "ctx": "0",
  "write": "app_status_led_write",
  "input_contract": "uint8_t",
  "input_type": "uint8_t"
}
```

`write` 签名：

```c
efw_status_t app_status_led_write(void *ctx, const void *cmd, uint16_t cmd_size);
```

### processor.custom

`processor.custom` 用于把上游数据转换成下游需要的 contract。可以完全手写处理函数：

```json
{
  "id": "battery_filter",
  "type": "processor.custom",
  "primary_input_port": "sensor",
  "input_contract": "float",
  "input_type": "float",
  "output_contract": "float",
  "output_type": "float",
  "output_size": 4,
  "output_align": 4,
  "process_mode": "full_custom",
  "output_mode": "custom_code",
  "process": "app_battery_filter_process"
}
```

也可以用字段映射组装结构体，例如把传感器 float 转成 PID 输入：

```json
{
  "id": "line_to_pid_input",
  "type": "processor.custom",
  "primary_input_port": "sensor",
  "output_contract": "efw_pid_input_t",
  "output_type": "efw_pid_input_t",
  "output_size": 16,
  "output_align": 4,
  "output_mode": "assemble_struct",
  "process_mode": "mapping_only",
  "field_mappings": [
    { "field": "setpoint", "source": "const", "value": 0.0, "transform": "identity" },
    { "field": "feedback", "source": "sensor", "path": "", "transform": "identity" },
    { "field": "dt", "source": "const", "value": 0.01, "transform": "identity" },
    { "field": "feedforward", "source": "const", "value": 0.0, "transform": "identity" }
  ]
}
```

可选值：

- `trigger_policy`: `primary_only`、`any_input`、`event_only`、`manual`
- `output_mode`: `passthrough`、`assemble_struct`、`scalar_compute`、`custom_code`
- `process_mode`: `full_custom`、`mapping_then_custom`、`mapping_only`
- `field_mappings[].source`: `sensor`、`processor`、`algorithm`、`event`、`module_input`、`const`、`expr`
- `field_mappings[].transform`: `identity`、`to_float`、`to_uint16`、`scale`、`offset`

### algorithm.pid

```json
{
  "id": "motor_pid",
  "type": "algorithm.pid",
  "kp": 1.2,
  "ki": 0.0,
  "kd": 0.1,
  "out_min": -100.0,
  "out_max": 100.0
}
```

`algorithm.pid` 输入固定是 `efw_pid_input_t`，输出固定是 `efw_pid_output_t`。普通 sensor 不能直接连 PID，中间需要 `processor.custom` 转换。

### algorithm.custom

```json
{
  "id": "custom_algo",
  "type": "algorithm.custom",
  "algo_type": "EFW_ALGO_CUSTOM",
  "ctx": "0",
  "run": "app_custom_algo_run",
  "primary_input_port": "processor",
  "output_contract": "float",
  "output_type": "float",
  "output_size": 4,
  "output_align": 4
}
```

`run` 签名：

```c
efw_status_t app_custom_algo_run(void *ctx, const efw_app_multi_input_t *in, void *out);
```

如果自定义算法要作为 `control.line_follower` 的 PID，需要写：

```json
"io_contract": "efw_pid"
```

### event.topic / publisher / subscriber

```json
{
  "id": "topic_battery",
  "type": "event.topic",
  "topic_id": 1,
  "payload_type": "float"
}
```

```json
{
  "id": "publish_battery",
  "type": "event.publisher",
  "topic": "topic_battery",
  "source": "battery_sensor",
  "data_expr": "&battery_voltage",
  "size_expr": "sizeof(battery_voltage)"
}
```

```json
{
  "id": "subscribe_battery",
  "type": "event.subscriber",
  "topic": "topic_battery",
  "target": "health_service",
  "callback": "app_on_battery_topic",
  "user": "0"
}
```

订阅回调签名固定为：

```c
void app_on_battery_topic(uint16_t topic_id, const void *data, uint16_t size, void *user);
```

### task.periodic

`task.periodic` 可以作为顶层 `tasks[]` 项，也可以作为 `nodes[]` 中的节点。两者都会进入统一调度表。

```json
{
  "id": "heartbeat_100ms",
  "type": "task.periodic",
  "period_ms": 100,
  "call": "app_heartbeat_100ms"
}
```

或调度某个 flow：

```json
{
  "id": "line_task_10ms",
  "type": "task.periodic",
  "period_ms": 10,
  "flow": "line_fast"
}
```

`period_ms` 必须大于 0，并且必须是 `project.tick_ms` 的整数倍。`call` 签名：

```c
efw_status_t app_heartbeat_100ms(void);
```

### state.machine / state.state / state.transition

```json
{ "id": "main_sm", "type": "state.machine", "initial": "idle" }
```

```json
{
  "id": "idle",
  "type": "state.state",
  "machine": "main_sm",
  "on_enter": "app_idle_enter",
  "on_update": "app_idle_update",
  "on_exit": "app_idle_exit"
}
```

```json
{
  "id": "idle_to_run",
  "type": "state.transition",
  "machine": "main_sm",
  "from": "idle",
  "to": "run",
  "condition": "app_should_run",
  "priority": 10,
  "timeout_ms": 0,
  "event_trigger": "event:start_button",
  "action": "app_on_start"
}
```

状态回调签名：

```c
efw_status_t app_idle_enter(void *ctx);
efw_status_t app_idle_update(void *ctx);
efw_status_t app_idle_exit(void *ctx);
```

条件函数签名：

```c
int app_should_run(void);
```

`event_trigger` 目前是语义标记/注释，支持 `topic:<event.topic节点id>` 或 `event:<事件名>`。

## edges

连线表达节点关系。每条 edge 必须引用存在的 `from` 和 `to` 节点。

```json
{
  "id": "edge_battery_to_filter",
  "from": "battery_sensor",
  "to": "battery_filter",
  "from_port": "sensor",
  "to_port": "sensor",
  "kind": "data_flow"
}
```

| 字段 | 类型 | 必填 | 说明 |
| ---- | ---- | ---- | ---- |
| `id` | string | 建议 | 连线 ID。未写时校验器按位置生成内部 ID，但推荐显式写唯一 ID。 |
| `from` | string | 是 | 起点节点 ID。 |
| `to` | string | 是 | 终点节点 ID。 |
| `from_port` | string | 否 | 起点端口，用于校验和自动补 contract。 |
| `to_port` | string | 否 | 终点端口，用于校验和自动补 contract。 |
| `kind` | string | 否 | 连线类型，默认 `generic`。 |

推荐使用的 `kind`：

- `hardware_dependency`: HAL 到 Sensor/Actuator。
- `data_flow`: Sensor/Processor/Algorithm/Module 的运行时数据流。
- `control_flow`: Algorithm/Processor 到 Actuator 的控制命令流。
- `event`: Topic/Publisher/Subscriber/Event 输入关系。
- `schedule`: Task 调度关系。
- `state_transition`: 状态机语义关系。
- `code`: 代码说明关系。
- `contains`: 分组/包含关系。
- `generic`: 说明性连接。

兼容旧 Graph 的别名也能被接受，例如 `data`、`control`、`state`、`containment`，但新文件建议使用上面的标准名称。

常用端口：

| 节点类型 | 输入端口 | 输出端口 |
| ---- | ---- | ---- |
| `hal.*` | 无 | `hal` |
| `sensor.custom` | `hal` | `sensor`, `event_source` |
| `sensor.line_tracking` | `hal` | `sensor` |
| `processor.custom` | `sensor`, `algorithm`, `event`, `module_input` | `processor`, `algorithm`, `control`, `module_output`, `event_source` |
| `algorithm.pid` | `sensor`, `processor` | `algorithm` |
| `algorithm.custom` | `sensor`, `processor`, `event` | `algorithm` |
| `actuator.motor` | `control`, `motor_pair` | `motor_pair` |
| `actuator.custom` | `hal`, `control` | 无 |
| `event.topic` | 无 | `topic` |
| `event.publisher` | `topic`, `event_source` | `event` |
| `event.subscriber` | `topic` | `event` |
| `module.custom` | `module_input`, `event`, `schedule` | `module`, `module_output`, `event_source` |
| `task.periodic` | 无 | `schedule` |
| `state.machine` | 无 | `state_machine` |
| `state.state` | `state_machine`, `transition_to` | `transition_from` |
| `state.transition` | `state_machine`, `transition_from` | `transition_to` |

部分输入端口只允许一条来源连线，例如 `sensor.custom.hal`、`algorithm.pid.processor`、`event.subscriber.topic`、`state.transition.transition_from`。

## contracts

Contract 描述运行时数据的 C 类型、大小和对齐。自动 dataflow 需要知道每条边两端 contract 是否一致，以及缓冲区要多大。

内置 contract：

| 名称 | C 类型 | size | align |
| ---- | ---- | ---- | ---- |
| `efw_pid_input_t` | `efw_pid_input_t` | 16 | 4 |
| `efw_pid_output_t` | `efw_pid_output_t` | 12 | 4 |
| `efw_motor_cmd_t` | `efw_motor_cmd_t` | 8 | 4 |
| `efw_line_tracking_data_t` | `efw_line_tracking_data_t` | 18 | 2 |
| `float` | `float` | 4 | 4 |
| `uint8_t` | `uint8_t` | 1 | 1 |
| `uint16_t` | `uint16_t` | 2 | 2 |
| `uint32_t` | `uint32_t` | 4 | 4 |

自定义 contract 示例：

```json
"contracts": [
  {
    "name": "battery_sample_t",
    "c_type": "battery_sample_t",
    "size": 8,
    "align": 4
  }
]
```

如果要让字段映射校验结构体字段，可以再加一个 `data.struct` 节点：

```json
{
  "id": "battery_sample_struct",
  "type": "data.struct",
  "name": "battery_sample_t",
  "fields": [
    { "name": "voltage", "type": "float" },
    { "name": "current", "type": "float" }
  ]
}
```

实际 C 类型定义仍然要放在 `custom_files` 或 `board_adapters` 中。

## flows

当前 `flows[]` 只支持 `control.line_follower`。

```json
{
  "id": "line_fast",
  "type": "control.line_follower",
  "sensor": "line_sensor",
  "pid": "line_pid",
  "left_motor": "left_motor",
  "right_motor": "right_motor",
  "weights": [-2.0, -1.0, 1.0, 2.0],
  "dt": 0.001,
  "period_ms": 1
}
```

规则：

- `sensor` 必须引用 `sensor.line_tracking`。
- `pid` 必须引用 `algorithm.pid` 或带 `io_contract=efw_pid` 的 `algorithm.custom`。
- `left_motor` 和 `right_motor` 必须引用 `actuator.motor`。
- `weights` 数量必须等于输入 HAL 的 `channels`。
- `period_ms` 必须是 `project.tick_ms` 的整数倍。

## custom_files 与 board_adapters

这两个字段都是文件数组，每项格式相同：

```json
{
  "path": "app_custom.c",
  "content": "#include \"efw/efw.h\"\n\nefw_status_t app_heartbeat_100ms(void) { return EFW_OK; }\n"
}
```

规则：

- `path` 必须是相对路径，不能覆盖生成器保留文件，例如 `app_bootstrap.c`、`app_platform.c`、`main.c`。
- `custom_files` 和 `board_adapters` 之间不能有重复 `path`。
- 生成器会扫描 `.c` 内容，检查回调函数是否存在、返回类型和参数是否匹配。
- 不要在自定义代码里定义生成器保留符号：`app_init`、`app_loop_1ms`、`app_loop_tick`、`app_platform_register`、`app_components_register`、`main`。

推荐分工：

- `custom_files`: 业务逻辑、算法、任务、模块、topic callback。
- `board_adapters`: 真实硬件读写，例如 `app_board_read_line_input()`、`app_board_write_motor()`、STM32 HAL/BSP glue。

## 完整例子：自定义传感器、任务和事件

```json
{
  "project": { "name": "battery_app", "tick_ms": 1 },
  "board": { "profile": "stm32-basic", "pin_plan": [] },
  "nodes": [
    { "id": "system_core", "type": "project.module", "display_name": "System Core" },
    {
      "id": "battery_sensor",
      "type": "sensor.custom",
      "sensor_type": "custom",
      "ctx": "0",
      "read": "app_battery_sensor_read",
      "output_contract": "float",
      "output_type": "float",
      "module": "system_core"
    },
    {
      "id": "topic_battery",
      "type": "event.topic",
      "topic_id": 1,
      "payload_type": "float",
      "module": "system_core"
    },
    {
      "id": "subscribe_battery",
      "type": "event.subscriber",
      "topic": "topic_battery",
      "callback": "app_on_battery_topic",
      "user": "0",
      "module": "system_core"
    }
  ],
  "edges": [
    {
      "id": "edge_topic_to_subscriber",
      "from": "topic_battery",
      "to": "subscribe_battery",
      "from_port": "topic",
      "to_port": "topic",
      "kind": "event"
    }
  ],
  "flows": [],
  "tasks": [
    { "id": "battery_sample_20ms", "type": "task.periodic", "period_ms": 20, "call": "app_battery_sample_20ms" }
  ],
  "custom_files": [
    {
      "path": "app_custom.c",
      "content": "#include \"efw/efw.h\"\n\nefw_status_t app_battery_sensor_read(void *ctx, void *out, uint16_t out_size) { EFW_UNUSED(ctx); EFW_UNUSED(out_size); if (out) *(float *)out = 7.4f; return EFW_OK; }\nefw_status_t app_battery_sample_20ms(void) { return EFW_OK; }\nvoid app_on_battery_topic(uint16_t topic_id, const void *data, uint16_t size, void *user) { EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user); }\n"
    }
  ],
  "board_adapters": [],
  "contracts": []
}
```

## 校验和生成

手写 Graph 后先校验，再生成：

```bash
python3 tools/efw.py codegen path/to/graph.json -o application/generated_my_app --dry-run
```

生成 application：

```bash
python3 tools/efw.py codegen path/to/graph.json -o application/generated_my_app --force
```

如果使用项目文件：

```bash
python3 tools/efw.py project validate examples/projects/generic_embedded_app.efw_project.json
python3 tools/efw.py project generate examples/projects/generic_embedded_app.efw_project.json --dry-run
```

## 常见错误

| 错误 | 原因 | 修复 |
| ---- | ---- | ---- |
| `nodes 不能为空数组` | 没有写节点。 | 至少添加一个 `project.module`。 |
| `节点 ID 重复` | 两个节点 `id` 一样。 | 改成唯一 ID。 |
| `module 引用了不存在的模块` | 节点 `module` 指向了不存在的 `project.module`。 | 添加模块节点或删除 `module` 字段。 |
| `callback must be a valid C identifier` | 回调名不是合法 C 标识符。 | 只用字母、数字、下划线，且不能以数字开头。 |
| `missing callback implementation` | Graph 声明了回调，但源码里没有函数定义。 | 在 `custom_files` 或 `board_adapters` 中实现对应函数。 |
| `period_ms must be a multiple of project.tick_ms` | 周期不能被 tick 整除。 | 调整 `project.tick_ms` 或 `period_ms`。 |
| `dataflow contract mismatch` | 连线两端 contract 不一致。 | 添加 `processor.custom` 做转换，或修正 `input_contract/output_contract`。 |
| `contract ... needs size for automatic dataflow` | 自动 dataflow 使用了未知大小的自定义类型。 | 在 `contracts[]` 或节点 `input_size/output_size` 中声明 size/align。 |
| `board_adapters path duplicates custom_files path` | 两个文件数组里路径重复。 | 保证每个 `path` 唯一。 |

## 写 Graph 的推荐顺序

1. 先写 `project`、`board` 和一个 `project.module`。
2. 添加 HAL/Sensor/Actuator/Algorithm/Module 节点，保证每个节点 `id` 唯一。
3. 给需要用户实现的节点填写回调名，并在 `custom_files`/`board_adapters` 中实现。
4. 添加 `edges`，明确 `kind`、`from_port`、`to_port`。
5. 如果出现数据类型转换，先声明 `contracts[]`，再用 `processor.custom` 转换。
6. 添加 `tasks[]` 或 `task.periodic` 节点，把业务函数或 flow 放入调度。
7. 运行 `--dry-run` 校验，修复错误后再生成。
