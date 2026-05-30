# EFW 代码生成器与 PyQt 可视化编辑器

`tools/efw_codegen.py` 是可视化蓝图系统的代码生成后端：它把 Graph JSON 生成可复制到真实工程的 `application/` 目录。`tools/efw_visual_editor.py` 是 PyQt 桌面编辑器：它提供卡片画布、连线辅助、节点 JSON 属性编辑、完整 Graph JSON 编辑、Code 标签页和一键生成入口。`tools/efw_project_manager.py` 在此基础上增加项目管理界面，用 `.efw_project.json` 记录 graph 路径、输出目录、板级 profile 和 notes。

当前版本定位为 **通用嵌入式 application 生成器**，循迹车只是一个内置 flow 示例。生成器现在支持：

- 多个 `control.line_follower` flow，并对 flow/task ID 做去重校验。
- `project.tick_ms` 作为真实调度基准，flow/task 的 `period_ms` 必须是它的整数倍。
- `tasks` 或 `task.periodic` 节点生成周期性自定义函数调用，也可以用 `task.flow` 精确调度某个 flow。
- `project.module` 用于把一个项目拆成多个模块/子系统，节点可用 `module` 字段归属到某个模块。
- `event.topic` / `event.publisher` / `event.subscriber` 用于可视化发布-订阅通信；订阅者会生成 `efw_topic_subscribe()` 绑定代码。
- `hal.custom`、`sensor.custom`、`actuator.custom`、`algorithm.custom`、`module.custom` 这类由用户代码实现的可注册卡片。
- `custom_files` 保存业务代码，`board_adapters` 保存板级适配代码；两者都会输出并加入 CMake 片段。
- 对自定义回调做静态校验：函数是否存在、签名是否匹配、`.c` 是否 include EFW/app 头、是否覆盖生成文件、是否和生成入口符号冲突。

## CLI 使用方法

在仓库根目录执行：

```bash
python3 tools/efw_codegen.py examples/graphs/generic_embedded_app.json \
  -o application/generated_generic_embedded_app \
  --force
```

循迹车示例：

```bash
python3 tools/efw_codegen.py examples/graphs/line_tracking_car.json \
  -o application/generated_line_tracking_car \
  --force
```

带自定义算法、模块和周期任务的循迹示例：

```bash
python3 tools/efw_codegen.py examples/graphs/line_tracking_car_with_custom_code.json \
  -o application/generated_line_tracking_car_custom \
  --force
```

生成目录包含：

```text
app_board_config.h        板级引脚、PWM 和常量
app_manifest.h            功能开关、registry pool 容量、APP_PROJECT_TICK_MS
app_bootstrap.c/.h        runtime glue、pool 初始化、flow bind、tick scheduler
app_platform.c/.h         HAL/SENSOR/ACTUATOR 注册和 mock BSP 回调
app_components.c/.h       PID、自定义算法和自定义模块注册
main.c                    极简入口，便于主机侧编译验证
CMakeLists.generated.txt  可选的 CMake 片段，会包含 custom_files/board_adapters 中的 .c 文件
```

## PyQt 项目管理与可视化编辑器

安装 PyQt6 或 PyQt5 后可以先启动项目管理界面：

```bash
python3 tools/efw_project_manager.py
```

项目管理界面用于维护 `.efw_project.json`，包括项目名、Graph JSON、输出 application 目录、板级 profile 和交接 notes。示例项目文件：

```text
examples/projects/generic_embedded_app.efw_project.json
```

也可以直接启动蓝图编辑器：

```bash
python3 tools/efw_visual_editor.py
```

编辑器包含三块核心区域：

- **Card Palette / Canvas**：添加并拖动 HAL、传感器、电机、PID、自定义算法、自定义模块、周期任务、说明卡片等。
- **Connect Selected**：在画布上选中两张卡后自动写入常见连接，例如 HAL → Sensor、HAL → Actuator、Sensor → PID/Custom Algorithm，减少手写 Graph JSON。
- **Properties**：每张卡片本质仍是 JSON，可以直接编辑参数。
- **Code**：为自定义算法、模块、任务或辅助函数添加 `.c/.h` 文件；这些文件保存在 `graph.custom_files` 中，并在生成 application 时一起输出。

可视化和代码不是互斥关系：推荐把稳定、通用的拓扑用卡片表达，把比赛中经常变化或很难抽象的自定义逻辑放到 Code 标签页或 `board_adapters`。

## Graph JSON 结构

示例文件在 `examples/graphs/generic_embedded_app.json`、`examples/graphs/line_tracking_car.json` 和 `examples/graphs/line_tracking_car_with_custom_code.json`。顶层包含：

- `project`：项目名和周期等元数据；`tick_ms` 是调度基准。
- `nodes`：蓝图节点列表，`id` 必须唯一。
- `flows`：控制流列表；当前支持多个 `control.line_follower`，`id` 必须唯一。
- `tasks`：可选的周期任务列表；也可以用 `task.periodic` 节点表示周期任务，`id` 必须唯一。
- `custom_files`：可选的用户自定义源码文件。
- `board_adapters`：可选的板级适配源码文件，适合放 STM32 HAL、ESP-IDF、DriverLib 或自有 BSP glue。

当前支持的节点类型：

| 类型 | 作用 |
| ---- | ---- |
| `hal.gpio_line_input` | 多路 GPIO/比较器循迹输入 |
| `hal.custom` | 通用 HAL 外设卡片，init/read/write/ioctl 回调由 `custom_files` 或 `board_adapters` 实现 |
| `sensor.line_tracking` | 绑定到输入 HAL 的循迹传感器 |
| `sensor.custom` | 自定义传感器，read/init 回调由 `custom_files` 或 `board_adapters` 实现 |
| `actuator.motor` | 电机执行器 |
| `actuator.custom` | 自定义执行器，write/init/enable/disable 回调由 `custom_files` 或 `board_adapters` 实现 |
| `algorithm.pid` | 内置 PID 控制器 |
| `algorithm.custom` | 自定义算法，run 回调由 `custom_files` 实现并注册为 `efw_algo_ops_t` |
| `module.custom` | 自定义模块，init/start/stop/poll 回调由 `custom_files` 实现并注册为 `efw_module_ops_t` |
| `task.periodic` | 周期任务卡片，生成到 tick scheduler 中 |
| `project.module` | 项目模块/子系统分组卡片，用于表达一个项目由多个模块组成 |
| `event.topic` | 事件总线 topic 定义卡片，生成 `APP_TOPIC_*` 宏 |
| `event.publisher` | 发布者说明卡片，用于表达某个模块/传感器会向 topic 发布数据 |
| `event.subscriber` | 订阅者卡片，会在 bind 阶段生成 `efw_topic_subscribe()` |
| `state.machine` / `state.state` / `state.transition` | 生成轻量状态机 glue：状态注册、当前状态索引、进入/更新/退出回调与条件转换 |
| `logic.if` / `logic.loop` | 生成 `app_logic_<id>()` wrapper；`logic.loop` 使用 `max_iterations` 防止不可控死循环 |
| `custom.card` | 纯说明/占位卡片，用于记录硬件、调参或未来模板 |
| `custom.code` | 自定义代码说明卡片，代码正文放在 `custom_files` |

## 模块分组与发布-订阅可视化

一个真实嵌入式项目通常不是单个大流程，而是由多个模块/子系统组成，例如 `power_module`、`motion_module`、`ui_module`。Graph 中可以添加 `project.module` 卡片，并在其它节点上填写 `module` 字段，把 HAL、Sensor、Algorithm、Module、Task、Event 卡片归属到对应模块。当前生成器会校验 `module` 引用是否存在；这一层主要用于可视化组织、文档交接和后续生成更细粒度的模块文件。

事件总线已经可以用三类卡片表达：

- `event.topic`：定义 `topic_id`、载荷类型和说明，并生成 `APP_TOPIC_<ID>` 宏。
- `event.publisher`：说明某个节点会向 topic 发布数据；具体 publish 调用通常写在用户模块或任务代码中。
- `event.subscriber`：声明订阅 topic 的回调，生成器会校验回调存在并在 `app_bind_handles()` 中生成 `efw_topic_subscribe(topic_id, callback, user)`。

订阅回调签名固定为：

```c
void app_on_xxx_topic(uint16_t topic_id, const void *data, uint16_t size, void *user);
```

这意味着通信方式不再只能靠手写 C 代码记忆，蓝图中可以直接看到“谁发布、谁订阅、topic ID 是多少”。

## 调度与 project.tick_ms

`project.tick_ms` 是生成应用每调用一次 `app_loop_tick()` 前进的时间。兼容旧代码，生成器也保留 `app_loop_1ms()`，它会转调 `app_loop_tick()`。

```json
"project": { "name": "generated_app", "tick_ms": 5 }
```

当 `tick_ms=5` 时，所有 `period_ms` 必须是 5 的整数倍，例如 5、10、20、100。生成器会拒绝 7ms 这类无法在当前 tick 下准确表达的周期。

## 多 flow / 多周期任务

每个 flow 都可以声明 `period_ms`：

```json
"flows": [
  { "id": "line_fast", "type": "control.line_follower", "period_ms": 1, ... },
  { "id": "line_slow", "type": "control.line_follower", "period_ms": 5, ... }
]
```

也可以让 task 显式调度某个 flow，避免 flow 自己按默认周期运行：

```json
"tasks": [
  { "id": "line_task_10ms", "type": "task.periodic", "period_ms": 10, "flow": "line_fast" },
  { "id": "battery_service_20ms", "type": "task.periodic", "period_ms": 20, "call": "app_custom_task_20ms" }
]
```

`call` 对应的函数必须存在，并且签名必须是：

```c
efw_status_t app_custom_task_20ms(void);
```

## 自定义算法或模块怎么办

原则是 **卡片 + 代码混合**：

1. 如果是框架内置且稳定的能力，例如 PID、电机、循迹传感器，用可视化卡片配置。
2. 如果是比赛现场临时写的算法、特殊模块、某块板子的私有 BSP、调参辅助函数，用 Code 标签页、`custom_files` 或 `board_adapters` 写 `.c/.h`。
3. 如果自定义逻辑以后变得通用，再把它沉淀为新的节点类型和生成模板。

自定义算法卡片示例：

```json
{
  "id": "custom_speed_limiter",
  "type": "algorithm.custom",
  "algo_type": "EFW_ALGO_CUSTOM",
  "ctx": "0",
  "run": "app_custom_algo_run"
}
```

如果自定义算法要接入 `control.line_follower` 的 `pid` 字段，则必须显式声明输入输出契约：

```json
{
  "id": "line_custom_pid",
  "type": "algorithm.custom",
  "io_contract": "efw_pid",
  "run": "app_line_custom_pid_run"
}
```

这表示 LineFollower 会传入 `const efw_pid_input_t *`，并期望输出 `efw_pid_output_t *`。函数签名仍然是统一算法接口：

```c
efw_status_t app_line_custom_pid_run(void *ctx, const void *in, void *out);
```

## 板级适配内置到生成流程

为了减少“生成后手动改 `app_platform.c`”的步骤，Graph 可以提供 `board_adapters`：

```json
"board_adapters": [
  {
    "path": "board_stm32_port.c",
    "content": "#include \"efw/efw.h\"\n..."
  }
]
```

推荐方式是：节点上只声明回调名，例如 `app_uart_debug_write`；真实 STM32 HAL / ESP-IDF / DriverLib glue 放在 `board_adapters`。生成器会检查这些函数确实存在、签名匹配，并把 `.c` 加入 `CMakeLists.generated.txt`。

## 生成代码的边界

生成器只生成 application 层，不修改 EFW 核心库。它既可以生成循迹车，也可以生成普通嵌入式项目（例如 UART 调试、传感器采样、LED/继电器执行器、后台服务和周期任务）。真实板卡移植时通常保留生成的注册结构，把板级读写放在 `board_adapters`：

1. `line_input_read()` / 自定义 HAL `read()`：接 GPIO、ADC、DMA、I2C/SPI/UART 等实际 BSP。
2. `motor_write()` / 自定义 Actuator `write()`：接 PWM、GPIO、CAN 电机或其他执行器。
3. 自定义 sensor/algorithm/module/task 的真实逻辑放在 `custom_files`，板级 glue 放在 `board_adapters`。

生成器会拒绝 `custom_files` / `board_adapters` 覆盖 `app_bootstrap.c`、`app_platform.c` 等核心生成文件，也会拒绝绝对路径、`..`、重复文件路径、缺失回调、不匹配签名和常见生成符号冲突。

## 可视化工作台近期增强

最新版本把项目管理器作为中文入口，建议优先运行：

```bash
python3 tools/efw_project_manager.py
```

它提供：

- **项目创建向导**：从通用嵌入式应用、循迹小车、循迹 + 自定义代码等模板创建 `.efw_project.json`。
- **统一项目入口**：项目名、Graph JSON、输出目录、Board Profile、notes、Validate、Generate 和蓝图编辑入口集中在一个窗口里，`tools/efw_visual_editor.py` 保留为高级直接编辑入口。
- **覆盖保护**：项目管理器和蓝图编辑器生成 application 时，如果输出目录已经存在且非空，会先弹出覆盖确认，不再无条件 `force=True`。
- **Board Profile 注入**：项目的 `board_profile` 会写入临时 Graph 的 `board.profile` 后再生成；蓝图编辑器的 Board Profile / Pin Planner 会把配置写回 `graph.board.profile` 和 `graph.board.pin_plan`。

蓝图编辑器也从“JSON 编辑器”增强为更接近蓝图的工作流：

- **属性表单**：选中卡片后优先显示键值表单；高级用户仍可切到原始 JSON 编辑复杂字段。
- **端口连线 + 统一 edges**：卡片左右两侧显示输入/输出端口，可从输出端口拖线到输入端口；连接会保存到 `graph.edges`，生成器会校验 edge 的端点是否存在，兼容旧的字段/flow 写法。
- **实时校验面板**：保存/刷新时运行 `validate_graph()` 并显示错误或生成摘要，同时展示统一 edge 数量和 Pin Planner 冲突。
- **代码生成映射视图**：展示每个节点、flow、task 会映射到哪些生成文件，方便排查“卡片为什么生成了这些 C 代码”。
- **项目结构 / 文件树 / 调度视图**：展示模块分组、Graph → application 文件树预览，以及 flow/task 的周期调度关系。
- **一键生成缺失回调**：根据 HAL/Sensor/Actuator/Algorithm/Module/Task/Event 节点声明，向 `app_custom.c` 追加缺失 callback stub。
- **自动布局**：将节点按类型粗略分列排列，适合导入 JSON 后快速整理画布。
- **模板库 / 组件市场感**：左侧面板按项目结构、硬件、传感器、执行器、算法、模块/任务、通信、状态机、逻辑控制、自定义分组展示模板，分组元数据已抽到 `tools/efw_visual_model.py`，作为后续拆分 PyQt 单文件的第一步。
- **分类配色**：画布卡片、端口和连线会按 HAL、Sensor、Actuator、Algorithm、Module、Task、Event、Project Module 等类型使用不同颜色，降低大型 Graph 的阅读成本。

> Code 面板目前仍是普通文本编辑器，适合先承载自定义算法、BSP glue 和临时代码。后续可以再增强为带语法高亮、符号索引和 LSP 的代码区。

## 生成能力边界

当前可视化卡片分为三类：

- **完整生成**：HAL/Sensor/Actuator/Algorithm/Module/Task、LineFollower flow 等会生成 C 注册、bind 或调度代码。
- **部分生成**：例如 `event.topic` 会生成 `APP_TOPIC_*` 宏，`event.subscriber` 会生成 `efw_topic_subscribe()`，但 `event.publisher` 的 `efw_topic_publish()` 调用仍应写在用户任务或模块代码中。
- **轻量生成**：`state.machine`、`state.state`、`state.transition`、`logic.if`、`logic.loop` 已生成可编译 glue，但业务条件和动作仍由 `custom_files` 回调实现。

编辑器的“生成映射”面板会显示每个节点的生成状态，避免用户误以为所有卡片都已经具备完整代码生成能力。

## 基础数据结构 API

`include/efw/core/ds.h` 提供无动态内存的基础数据结构，并通过 `efw/efw.h` 直接暴露：

- `efw_ringbuf_t`：字节环形缓冲区，适合 UART RX/TX、日志缓存、流式协议缓存。
- `efw_queue_t`：固定元素大小 FIFO 队列，适合事件、命令、采样结果排队。
- `efw_stack_t`：固定元素大小 LIFO 栈，适合轻量状态回退、解析器临时栈。

示例：

```c
#include "efw/efw.h"

uint8_t rx_mem[128];
efw_ringbuf_t rx_rb;
efw_ringbuf_init(&rx_rb, rx_mem, sizeof(rx_mem));
efw_ringbuf_push(&rx_rb, byte);
```

## 可视化能力与生成能力同步（新增）

为了避免“UI 卡片比代码生成走得更快”，编辑器现在把每种节点的生成状态显式展示在“生成映射”面板中：

- 左侧模板库会扫描 `include/efw/device/sensor`、`include/efw/device/actuator`、`include/efw/algorithm` 下的框架头文件，并把可安全映射到现有 Graph schema 的条目放入“框架库扫描”分组。
- 右侧属性表单对 `module`、`hal_name`、`topic`、`machine`、状态转换 `from/to`、`hal_type`、`sensor_type`、`actuator_type` 等字段使用下拉选择，减少手写字符串引用错误。
- `state.machine`、`state.state`、`state.transition` 已从占位升级为生成轻量状态机 glue：生成状态注册、当前状态索引、`on_enter/on_update/on_exit` 调用以及带 `condition` 的转换判断。
- `logic.if` 和 `logic.loop` 已从占位升级为生成 `app_logic_<id>()` wrapper；循环节点带 `max_iterations` 防护，避免在裸机主循环里产生不可控死循环。
- `project.module` 仍然是项目结构分组，但在可视化编辑器中可双击进入子模块页面，根视图/模块视图之间可以切换。
- Board Profile 数据库位于 `examples/board_profiles/board_profiles.json`，当前内置 `generic-mock`、`stm32-basic`、`esp32-basic`，Pin Planner 会基于 profile 生成默认资源规划草稿并检查冲突。
- 端口连线现在会先调用统一连接语义，只有合法连接才写入 `graph.edges`；无效连接会高亮并提示。
- 生成前会展示 create/overwrite/same/preserve 摘要；`--force` 和 UI 覆盖只覆盖生成目标文件，不再清空整个输出目录，因此额外用户文件会保留。

状态机节点的推荐连接方式：

```text
[state.machine] -> [state.state]
[state.state] -> [state.transition] -> [state.state]
```

`state.transition.condition` 必须是 `int condition(void)` / `uint8_t condition(void)` / `bool condition(void)` 风格的用户函数；状态回调使用 `efw_status_t callback(void *ctx)`。编辑器的“一键生成缺失回调”可以生成这些函数 stub。

### 本轮针对 UI/codegen 同步的补充

- “框架库扫描”不再只是空分类：编辑器会递归扫描 `include/efw` 下可映射到当前 schema 的 HAL、Sensor、Actuator、Algorithm、Module、Event、State 头文件，并把扫描来源写入卡片的 `framework_header` 字段。
- 右侧属性表单继续保留表格布局，但常见引用字段已经变成下拉选择器；复杂数组/对象仍放在高级 JSON 区编辑。
- `project.module` 现在支持双击进入模块视图；在模块视图里新建非模块卡片会自动归属当前模块，工具栏可返回根项目。
- 生成预览增加 `backup+overwrite` 状态；实际生成覆盖已有生成文件前会把旧内容保存到 `.efw_backup/`，额外用户文件仍标记为 `preserve` 并保持不动。
- 卡片摘要进一步包含 PID 参数、transition 条件、logic 条件、motor PWM/DIR 和 GPIO 输入首个引脚，方便在大图里快速辨认节点。
