# EFW 代码生成器（第一阶段）

`tools/efw_codegen.py` 是可视化蓝图系统的第一步：它先不做 UI，而是把一个机器可读的图描述 JSON 生成可复制到真实工程的 `application/` 目录。

当前版本是 **MVP 生成器**，只覆盖一个完整闭环：

```text
GPIO 循迹输入 → 循迹传感器 → PID → LineFollower → 左右电机
```

这对应可视化界面第一版最重要的节点集合：传感器、电机、PID、1ms 循迹控制流。

## 使用方法

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

当前支持的控制流类型：

| 类型 | 作用 |
| ---- | ---- |
| `control.line_follower` | 绑定循迹传感器、PID、左右电机并生成 1ms update |

## 生成代码的边界

生成器只生成 application 层，不修改 EFW 核心库。真实板卡移植时通常只需要保留生成的注册结构，然后修改 `app_platform.c` 中两个位置：

1. `line_input_read()`：把 mock 数组读取替换为 GPIO/ADC/DMA 数据读取。
2. `motor_write()`：把速度和方向写入替换为 PWM 占空比和 GPIO 方向控制。

这样可以保持可视化生成的业务拓扑不变，只替换底层 BSP 适配。
