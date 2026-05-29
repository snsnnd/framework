# EFW 代码生成器与 PyQt 可视化编辑器

`tools/efw_codegen.py` 是可视化蓝图系统的代码生成后端：它把一个机器可读的图描述 JSON 生成可复制到真实工程的 `application/` 目录。`tools/efw_visual_editor.py` 是第二步的 PyQt 桌面编辑器：它提供卡片画布、属性 JSON 编辑、代码编辑区和一键生成入口。

当前版本仍是 **MVP 生成器**，主要覆盖一个完整闭环：

```text
GPIO 循迹输入 → 循迹传感器 → PID → LineFollower → 左右电机
```

这对应可视化界面第一版最重要的节点集合：传感器、电机、PID、1ms 循迹控制流。

## CLI 使用方法

在仓库根目录执行：

```bash
python3 tools/efw_codegen.py examples/graphs/line_tracking_car.json \
  -o application/generated_line_tracking_car \
  --force
```

生成目录包含：

```text
app_board_config.h        板级引脚、PWM、速度和周期参数
app_manifest.h            功能开关、registry pool 容量、注册名称
app_bootstrap.c/.h        runtime glue、pool 初始化、handle bind、1ms update
app_platform.c/.h         HAL/SENSOR/ACTUATOR 注册和 mock BSP 回调
app_components.c/.h       PID 算法实例和注册
main.c                    极简入口，便于主机侧编译验证
CMakeLists.generated.txt  可选的 CMake 片段
```

## PyQt 可视化编辑器

安装 PyQt6 或 PyQt5 后可以启动桌面编辑器：

```bash
python3 tools/efw_visual_editor.py
```

编辑器包含三块核心区域：

- **Card Palette / Canvas**：添加并拖动 HAL、传感器、电机、PID、custom.code 等卡片。
- **Properties**：每张卡片本质仍是 JSON，可以直接编辑参数。
- **Code**：为自定义算法、模块或辅助函数添加 `.c/.h` 文件；这些文件会保存在 `graph.custom_files` 中，并在生成 application 时一起输出。

可视化和代码不是互斥关系：推荐把稳定、通用的拓扑用卡片表达，把比赛中经常变化或很难抽象的自定义逻辑放到 Code 标签页。

## Graph JSON 结构

示例文件在 `examples/graphs/line_tracking_car.json`。顶层包含：

- `project`：项目名和周期等元数据。
- `nodes`：蓝图节点列表。
- `flows`：控制流列表；MVP 版本只支持一个 `control.line_follower`。

当前支持的节点类型：

| 类型 | 作用 |
| ---- | ---- |
| `hal.gpio_line_input` | 多路 GPIO/比较器循迹输入 |
| `sensor.line_tracking` | 绑定到输入 HAL 的循迹传感器 |
| `actuator.motor` | 电机执行器 |
| `algorithm.pid` | PID 控制器 |
| `custom.code` | 自定义代码说明卡片，代码正文放在 `custom_files` |

当前支持的控制流类型：

| 类型 | 作用 |
| ---- | ---- |
| `control.line_follower` | 绑定循迹传感器、PID、左右电机并生成 1ms update |

## 自定义算法或模块怎么办

第二阶段的原则是 **卡片 + 代码混合**：

1. 如果是框架内置且稳定的能力，例如 PID、电机、循迹传感器，用可视化卡片配置。
2. 如果是比赛现场临时写的算法、特殊模块、某块板子的私有 BSP、调参辅助函数，用 Code 标签页写 `.c/.h`。
3. 如果自定义逻辑以后变得通用，再把它沉淀为新的节点类型和生成模板。

Graph 中的 `custom_files` 示例：

```json
"custom_files": [
  {
    "path": "app_custom.c",
    "content": "#include \"efw/efw.h\"\n\nvoid app_custom_user_hook(void) {}\n"
  }
]
```

生成器会拒绝 `custom_files` 覆盖 `app_bootstrap.c`、`app_platform.c` 等核心生成文件，也会拒绝绝对路径和 `..`，避免误写出 application 目录。`.c` 自定义文件会自动加入 `CMakeLists.generated.txt`。

## 生成代码的边界

生成器只生成 application 层，不修改 EFW 核心库。真实板卡移植时通常只需要保留生成的注册结构，然后修改 `app_platform.c` 中两个位置：

1. `line_input_read()`：把 mock 数组读取替换为 GPIO/ADC/DMA 数据读取。
2. `motor_write()`：把速度和方向写入替换为 PWM 占空比和 GPIO 方向控制。

这样可以保持可视化生成的业务拓扑不变，只替换底层 BSP 适配。
