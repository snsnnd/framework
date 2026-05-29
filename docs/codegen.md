# EFW 代码生成器与 PyQt 可视化编辑器

`tools/efw_codegen.py` 是可视化蓝图系统的代码生成后端：它把 Graph JSON 生成可复制到真实工程的 `application/` 目录。`tools/efw_visual_editor.py` 是 PyQt 桌面编辑器：它提供卡片画布、节点 JSON 属性编辑、完整 Graph JSON 编辑、Code 标签页和一键生成入口。

当前版本不再只绑定单个循迹小车模板，而是支持：

- 多个 `control.line_follower` flow。
- 每个 flow 独立的 `period_ms` 调度周期。
- `tasks` 或 `task.periodic` 节点生成周期性自定义函数调用。
- `sensor.custom`、`algorithm.custom`、`module.custom` 这类由用户代码实现的可注册卡片。
- `custom_files` 将自定义 `.c/.h` 文件和可视化拓扑一起保存、一起输出。

## CLI 使用方法

在仓库根目录执行：

```bash
python3 tools/efw_codegen.py examples/graphs/line_tracking_car.json \
  -o application/generated_line_tracking_car \
  --force
```

通用嵌入式应用示例（没有循迹车依赖，只包含自定义 HAL/SENSOR/ACTUATOR/MODULE/TASK）：

```bash
python3 tools/efw_codegen.py examples/graphs/generic_embedded_app.json \
  -o application/generated_generic_embedded_app \
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
app_board_config.h        板级引脚、PWM、速度和周期参数
app_manifest.h            功能开关、registry pool 容量
app_bootstrap.c/.h        runtime glue、pool 初始化、flow bind、1ms scheduler
app_platform.c/.h         HAL/SENSOR/ACTUATOR 注册和 mock BSP 回调
app_components.c/.h       PID、自定义算法和自定义模块注册
main.c                    极简入口，便于主机侧编译验证
CMakeLists.generated.txt  可选的 CMake 片段，会包含 custom_files 中的 .c 文件
```

## PyQt 可视化编辑器

安装 PyQt6 或 PyQt5 后可以启动桌面编辑器：

```bash
python3 tools/efw_visual_editor.py
```

编辑器包含三块核心区域：

- **Card Palette / Canvas**：添加并拖动 HAL、传感器、电机、PID、自定义算法、自定义模块、周期任务、说明卡片等。
- **Properties**：每张卡片本质仍是 JSON，可以直接编辑参数。
- **Code**：为自定义算法、模块、任务或辅助函数添加 `.c/.h` 文件；这些文件保存在 `graph.custom_files` 中，并在生成 application 时一起输出。

可视化和代码不是互斥关系：推荐把稳定、通用的拓扑用卡片表达，把比赛中经常变化或很难抽象的自定义逻辑放到 Code 标签页。

## Graph JSON 结构

示例文件在 `examples/graphs/generic_embedded_app.json`、`examples/graphs/line_tracking_car.json` 和 `examples/graphs/line_tracking_car_with_custom_code.json`。顶层包含：

- `project`：项目名和周期等元数据。
- `nodes`：蓝图节点列表。
- `flows`：控制流列表；当前支持多个 `control.line_follower`。
- `tasks`：可选的周期任务列表；也可以用 `task.periodic` 节点表示周期任务。
- `custom_files`：可选的用户自定义源码文件。

当前支持的节点类型：

| 类型 | 作用 |
| ---- | ---- |
| `hal.gpio_line_input` | 多路 GPIO/比较器循迹输入 |
| `hal.custom` | 通用 HAL 外设卡片，init/read/write/ioctl 回调由 `custom_files` 实现 |
| `sensor.line_tracking` | 绑定到输入 HAL 的循迹传感器 |
| `sensor.custom` | 自定义传感器，read/init 回调由 `custom_files` 实现 |
| `actuator.motor` | 电机执行器 |
| `actuator.custom` | 自定义执行器，write/init/enable/disable 回调由 `custom_files` 实现 |
| `algorithm.pid` | 内置 PID 控制器 |
| `algorithm.custom` | 自定义算法，run 回调由 `custom_files` 实现并注册为 `efw_algo_ops_t` |
| `module.custom` | 自定义模块，init/start/stop/poll 回调由 `custom_files` 实现并注册为 `efw_module_ops_t` |
| `task.periodic` | 周期任务卡片，生成到 1ms scheduler 中 |
| `custom.card` | 纯说明/占位卡片，用于记录硬件、调参或未来模板 |
| `custom.code` | 自定义代码说明卡片，代码正文放在 `custom_files` |

当前支持的控制流类型：

| 类型 | 作用 |
| ---- | ---- |
| `control.line_follower` | 绑定循迹传感器、PID/自定义算法、左右电机并按 `period_ms` 调度 |

## 多 flow / 多周期任务

每个 flow 都可以声明 `period_ms`：

```json
"flows": [
  { "id": "line_fast", "type": "control.line_follower", "period_ms": 1, ... },
  { "id": "line_slow", "type": "control.line_follower", "period_ms": 5, ... }
]
```

生成的 `app_bootstrap.c` 会创建 `g_app_tick_ms`，在 `app_loop_1ms()` 中按周期调用不同 flow。自定义周期任务可以写在 `tasks`：

```json
"tasks": [
  { "id": "battery_service_20ms", "type": "task.periodic", "period_ms": 20, "call": "app_custom_task_20ms" }
]
```

`call` 对应的 `efw_status_t app_custom_task_20ms(void)` 函数由 Code 标签页或 `custom_files` 提供。

## 自定义算法或模块怎么办

原则是 **卡片 + 代码混合**：

1. 如果是框架内置且稳定的能力，例如 PID、电机、循迹传感器，用可视化卡片配置。
2. 如果是比赛现场临时写的算法、特殊模块、某块板子的私有 BSP、调参辅助函数，用 Code 标签页写 `.c/.h`。
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

自定义模块卡片示例：

```json
{
  "id": "custom_health_module",
  "type": "module.custom",
  "module_type": "EFW_MODULE_SERVICE",
  "ctx": "0",
  "init": "app_custom_module_init",
  "poll": "app_custom_module_poll"
}
```

生成器会为这些卡片生成注册代码，但不会替你实现回调函数；回调函数应放到 `custom_files` 中。

## 生成代码的边界

生成器只生成 application 层，不修改 EFW 核心库。它既可以生成循迹车，也可以生成普通嵌入式项目（例如 UART 调试、传感器采样、LED/继电器执行器、后台服务和周期任务）。真实板卡移植时通常保留生成的注册结构，然后修改 `app_platform.c` 中的 mock 读写：

1. `line_input_read()`：把 mock 数组读取替换为 GPIO/ADC/DMA 数据读取。
2. `motor_write()`：把速度和方向写入替换为 PWM 占空比和 GPIO 方向控制。
3. 自定义 sensor/algorithm/module/task 的真实逻辑放在 `custom_files`。

生成器会拒绝 `custom_files` 覆盖 `app_bootstrap.c`、`app_platform.c` 等核心生成文件，也会拒绝绝对路径和 `..`，避免误写出 application 目录。
