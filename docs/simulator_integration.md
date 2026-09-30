# 仿真器整合完成

## 新增功能

### 1. 性能检测模块

文件：`tools/simulator/perf.py`

功能：
- **PerformanceMonitor**: 实时性能监控
  - 帧时间、CPU 时间
  - 仿真速度（相对于实时）
  - 外设访问统计
  - 任务执行分析
  - 中断统计

- **PerformanceBenchmark**: 性能基准测试
  - CPU 计算性能
  - 内存访问速度
  - 外设访问速度
  - 仿真性能

### 2. Tools 整合

在 `tools/efw.py` 中添加了两个新命令：

#### simulator 命令

```bash
# 列出可用芯片
python3 tools/efw.py simulator list

# 查看芯片信息
python3 tools/efw.py simulator info STM32F407VGT6

# 运行仿真
python3 tools/efw.py simulator run --chip STM32F407VGT6 --duration 1000

# 运行基准测试
python3 tools/efw.py simulator benchmark --chip STM32F407VGT6
```

#### mcu 命令

```bash
# 扫描数据库
python3 tools/efw.py mcu scan

# 导入芯片
python3 tools/efw.py mcu import
python3 tools/efw.py mcu import --family STM32F4
python3 tools/efw.py mcu import --common

# 列出已导入芯片
python3 tools/efw.py mcu list

# 查看芯片信息
python3 tools/efw.py mcu info STM32F407VGT6

# 导出芯片数据
python3 tools/efw.py mcu export STM32F407VGT6 --format efw
```

---

## 使用示例

### 运行仿真并查看性能

```bash
# 运行 1 秒仿真
python3 tools/efw.py simulator run --chip STM32F407VGT6 --duration 1000

# 输出：
# ============================================================
# 仿真器性能报告
# ============================================================
# 运行状态:
#   运行时间: 4.3 秒
#   帧数量: 1
#   FPS: 0.2
#
# 当前帧:
#   帧时间: 4258.742 ms
#   CPU 时间: 4258.742 ms
#   仿真速度: 0.02x
#   周期数: 16,800,000
#   指令数: 16,800,000
# ============================================================
```

### 在代码中使用性能监控

```python
from tools.simulator.core import MCUSimulator
from tools.simulator.perf import PerformanceMonitor

# 创建 MCU 和监控器
mcu = MCUSimulator.from_chip("STM32F407VGT6")
monitor = PerformanceMonitor()
monitor.start()

# 仿真循环
for _ in range(1000):
    monitor.begin_frame()
    monitor.begin_task("control_loop")
    
    # 仿真代码
    mcu.tick(168000)  # 1ms
    
    monitor.end_task()
    monitor.end_frame(cycles=168000, instructions=168000)

# 获取报告
print(monitor.get_performance_report())
print(monitor.get_task_report())
```

---

## 文件结构

```
framework/
├── tools/simulator/
│   ├── core.py           # MCU 核心（支持真实芯片）
│   ├── chip_db.py        # 芯片数据库
│   ├── perf.py           # 性能检测模块（新增）
│   └── ...
│
└── tools/
    ├── efw.py            # 统一入口（已更新）
    ├── stm32_toolkit.py  # MCU 导入工具
    └── ...
```

---

## 命令总览

| 命令 | 说明 |
|------|------|
| `python3 tools/efw.py simulator list` | 列出可用芯片 |
| `python3 tools/efw.py simulator info <chip>` | 查看芯片信息 |
| `python3 tools/efw.py simulator run --chip <chip>` | 运行仿真 |
| `python3 tools/efw.py simulator benchmark` | 性能基准测试 |
| `python3 tools/efw.py mcu scan` | 扫描数据库 |
| `python3 tools/efw.py mcu import` | 导入芯片 |
| `python3 tools/efw.py mcu list` | 列出已导入芯片 |
| `python3 tools/efw.py mcu info <chip>` | 查看芯片信息 |
| `python3 tools/efw.py mcu export <chip>` | 导出芯片数据 |
