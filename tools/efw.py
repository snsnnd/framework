#!/usr/bin/env python3
"""
EFW CLI 用户工具链

面向嵌入式开发者的完整工作流：
  芯片选择 → 项目设计 → 代码生成 → 仿真验证 → 在线调试 → 烧录运行

使用方式：
  # 芯片管理
  python3 tools/efw.py mcu list
  python3 tools/efw.py mcu info STM32F407VGT6
  
  # 项目设计
  python3 tools/efw.py design --chip STM32F407VGT6 -o project.json
  
  # 代码生成
  python3 tools/efw.py develop project.json -o app/
  
  # 仿真验证
  python3 tools/efw.py simulate --chip STM32F407VGT6 --duration 1000
  
  # 在线调试
  python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
  python3 tools/efw.py debug record --port /dev/ttyUSB0 -o log.jsonl
  
  # 烧录运行
  python3 tools/efw.py flash --port COM3 --bin app.bin
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Optional


# ─── 帮助信息 ────────────────────────────────────────────────────────────────

HELP_TEXT = """
EFW CLI 用户工具链

用法: python3 tools/efw.py <command> [options]

命令:
  help                    显示帮助信息

  # 项目中心工作流（推荐）
  project create          创建 EFW 项目
  project info/list       查看项目
  project set/rename      编辑项目配置
  project graph           读取/导出/格式化 Graph
  project validate        校验 Graph
  project generate        生成 application
  project build           构建项目 application
  project simulate        按项目目标运行 MCU 仿真
  project flash           烧录项目固件
  project debug           Graph 运行流分析
  project device          真实设备 snapshot/record/analyze

  # 数据和底层工具
  board list/info/import  管理 Board Profile
  mcu list/info/import    管理 MCU 数据
  svd import/list/info    导入 SVD 并生成启动/链接文件
  firmware list/download  管理厂商固件包
  codegen <graph>         从 Graph JSON 生成 application
  build detect/compile    编译器底层入口
  hw pins/check/generate  硬件配置底层入口
  debug snapshot/record   真实设备调试底层入口
  flash --bin <file>      烧录底层入口

  # UI 和兼容入口
  studio                  启动 EFW Studio（可视化前端）
  design/develop          旧兼容入口，建议改用 project create/generate

示例:
  # 完整工作流
  python3 tools/efw.py project create demo --chip STM32F407VGT6 --board Discovery_F407
  python3 tools/efw.py project validate demo
  python3 tools/efw.py project generate demo --dry-run
  python3 tools/efw.py project build demo --generate
  python3 tools/efw.py project simulate demo --duration 1000
  python3 tools/efw.py project device demo snapshot --port /dev/ttyUSB0
  python3 tools/efw.py studio
"""


def print_help():
    """打印帮助信息"""
    print(HELP_TEXT)


def print_command_help(command: str):
    """打印命令帮助"""
    helps = {
        "mcu": """用法: python3 tools/efw.py mcu <subcommand>

子命令:
  list                列出可用芯片
  info <chip>         显示芯片信息
  import              导入芯片数据（交互式）

示例:
  python3 tools/efw.py mcu list
  python3 tools/efw.py mcu info STM32F407VGT6
  python3 tools/efw.py mcu import --family STM32F4""",
        
        "firmware": """用法: python3 tools/efw.py firmware <subcommand>

固件管理，从 GitHub 下载和管理嵌入式固件库。

子命令:
  list                列出支持的固件
  installed           查看已安装固件
  download <name>     下载固件
  remove <name>       删除固件
  info <name>         查看固件信息
  config --chip CHIP  配置项目使用固件

示例:
  python3 tools/efw.py firmware list
  python3 tools/efw.py firmware download stm32f4
  python3 tools/efw.py firmware installed
  python3 tools/efw.py firmware config --chip STM32F407VGT6""",
        
        "design": """用法: python3 tools/efw.py design --chip <chip> [-o output]

生成项目配置文件，包含芯片信息、外设映射、引脚配置。

选项:
  --chip CHIP         芯片名称（如 STM32F407VGT6）
  -o, --output FILE   输出文件路径（默认 project.json）

示例:
  python3 tools/efw.py design --chip STM32F407VGT6 -o my_project.json""",

        "project": """用法: python3 tools/efw.py project <subcommand>

项目管理工具，复用 Studio 的 .efw_project.json + graph.json 格式。

子命令:
  create <name>             创建项目
  list                      列出项目
  info <project>            查看项目详情
  validate <project>        校验项目 Graph
  generate <project>        生成 application
  build <project>           构建项目输出目录
  simulate <project>        按项目目标运行 MCU 仿真
  flash <project>           烧录项目固件
  debug <project>           查看运行流分析
  device <project> <action>  真实设备 snapshot/record/analyze
  set <project> ...         编辑项目配置
  rename <project> <name>   重命名项目
  clone <project> <name>    克隆项目
  graph <project> ...       读取/导出/格式化 Graph
  delete <project> --yes    删除托管项目
  recent                    查看最近项目

示例:
  python3 tools/efw.py project create demo --chip STM32F407VGT6 --board Discovery_F407
  python3 tools/efw.py project validate demo
  python3 tools/efw.py project generate demo --dry-run
  python3 tools/efw.py project debug demo --section scheduler
  python3 tools/efw.py project graph demo info
  python3 tools/efw.py project set demo --board Discovery_F407
  python3 tools/efw.py project list""",

        "board": """用法: python3 tools/efw.py board <subcommand>

Board/Profile 管理。

子命令:
  list                  列出 Board Profiles
  info <profile>        查看 profile JSON
  import <file>         导入 profile JSON 到 data/board_profiles
  set <project> <name>  设置项目 Board Profile

示例:
  python3 tools/efw.py board list
  python3 tools/efw.py board info Discovery_F407
  python3 tools/efw.py board set demo Discovery_F407""",

        "svd": """用法: python3 tools/efw.py svd <subcommand>

SVD 数据导入与启动/链接文件生成。

子命令:
  import <file.svd>     导入 SVD
  import-all <dir>      批量导入 SVD
  info <file.svd>       查看 SVD 信息
  list                  列出已导入芯片
  linker <chip>         生成 linker.ld
  startup <chip>        生成 startup 文件

示例:
  python3 tools/efw.py svd list
  python3 tools/efw.py svd import STM32F407.svd --name STM32F407VGT6
  python3 tools/efw.py svd linker STM32F407VGT6 -o linker.ld""",
        
        "develop": """用法: python3 tools/efw.py develop <config> [-o output]

旧兼容入口：从项目配置或 Graph 生成应用代码框架。新项目建议使用 `project generate`。

参数:
  config              项目配置文件路径

选项:
  -o, --output DIR    输出目录（默认 application/）

示例:
  python3 tools/efw.py develop project.json -o src/""",
        
        "simulate": """用法: python3 tools/efw.py simulate --chip <chip> [options]

运行 MCU 仿真，验证代码逻辑。

选项:
  --chip CHIP         芯片名称
  --duration MS       仿真时长（毫秒，默认 1000）
  --report            生成性能报告

示例:
  python3 tools/efw.py simulate --chip STM32F407VGT6 --duration 5000""",
        
        "debug": """用法: python3 tools/efw.py debug <subcommand> [options]

在线调试，连接真实 MCU 进行数据采集和分析。

子命令:
  snapshot            获取当前状态快照
  record              录制运行数据
  analyze             分析录制数据

选项:
  --port PORT         串口设备（如 /dev/ttyUSB0 或 COM3）
  --baud BAUD         波特率（默认 115200）
  -o, --output FILE   输出文件
  --duration SEC      录制时长（秒）

示例:
  python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
  python3 tools/efw.py debug record --port /dev/ttyUSB0 -o log.jsonl --duration 60""",
        
        "flash": """用法: python3 tools/efw.py flash [options]

烧录固件到 MCU。

选项:
  --bin FILE          固件文件路径
  --port PORT         串口/调试器端口
  --tool TOOL         烧录工具（stlink, jlink, openocd）
  --erase             烧录前擦除

示例:
  python3 tools/efw.py flash --bin build/app.bin --port COM3 --tool stlink""",
        
        "build": """用法: python3 tools/efw.py build <subcommand>

编译工具，管理 ARM GCC 编译器和项目构建。

子命令:
  check               检查编译器状态
  install             安装 ARM GCC 编译器
  init [chip]         初始化项目结构
  config --chip CHIP  配置项目（生成 CMake 缓存）
  compile             编译项目
  clean               清理构建目录

示例:
  python3 tools/efw.py build check
  python3 tools/efw.py build install
  python3 tools/efw.py build init STM32F407VGT6
  python3 tools/efw.py build config --chip STM32F407VGT6
  python3 tools/efw.py build compile
  python3 tools/efw.py build clean""",
        
        "hw": """用法: python3 tools/efw.py hw <subcommand>

硬件配置工具，管理引脚配置和外设配置。

子命令:
  pins --chip CHIP        列出芯片引脚
  check --config FILE     检查引脚冲突
  generate --config FILE  生成配置代码

选项:
  --chip CHIP             芯片名称
  --config FILE           配置文件路径
  -o, --output DIR        输出目录

示例:
  python3 tools/efw.py hw pins --chip STM32F407VGT6
  python3 tools/efw.py hw check --config hw_config.json
  python3 tools/efw.py hw generate --config hw_config.json -o src/""",
    }
    
    print(helps.get(command, f"没有 '{command}' 的帮助信息"))


def ensure_project_imports() -> None:
    """Make repo root and tools packages importable from any CLI entrypoint."""
    tools_dir = Path(__file__).resolve().parent
    project_root = tools_dir.parent
    for path in (project_root, tools_dir):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


# ─── 芯片管理 ────────────────────────────────────────────────────────────────

def cmd_mcu(argv: list[str]) -> int:
    """芯片管理"""
    ensure_project_imports()
    
    if not argv:
        print_command_help("mcu")
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd in {"help", "-h", "--help"}:
        print_command_help("mcu")
        return 0
    
    if subcmd == "list":
        from tools.simulator.chip_db import get_chip_database
        
        db = get_chip_database()
        if not db.available:
            print("芯片数据库不可用，请先导入:")
            print("  python3 tools/efw.py mcu import")
            return 1
        
        chips = db.list_chips()
        print(f"\n可用芯片 ({len(chips)} 个):")
        print("-" * 60)
        for chip in chips:
            info = db.get_chip_info(chip)
            print(f"  {chip}: {info.get('family')}, {info.get('core')}, {info.get('frequency_mhz')} MHz")
        return 0
    
    elif subcmd == "info":
        chip_name = rest[0] if rest else None
        if not chip_name:
            print("错误: 请指定芯片名称")
            return 1
        
        from tools.simulator.chip_db import get_chip_database
        db = get_chip_database()
        chip = db.load_chip(chip_name)
        
        if not chip:
            print(f"未找到芯片: {chip_name}")
            return 1
        
        print(f"\n芯片信息: {chip_name}")
        print("=" * 60)
        print(f"  系列: {chip.get('family')}")
        print(f"  核心: {chip.get('core')}")
        print(f"  频率: {chip.get('frequency_mhz')} MHz")
        print(f"  Flash: {chip.get('flash_kb')} KB")
        print(f"  RAM: {chip.get('ram_kb')} KB")
        print(f"  GPIO: {chip.get('gpio_count')} 个")
        
        peripherals = chip.get("peripherals", {})
        print("\n外设:")
        print(f"  ADC: {peripherals.get('adc', {}).get('count', 0)} 通道")
        print(f"  PWM: {peripherals.get('pwm', {}).get('count', 0)} 路")
        print(f"  UART: {list(peripherals.get('uart', {}).get('ports', {}).keys())}")
        print(f"  I2C: {list(peripherals.get('i2c', {}).get('ports', {}).keys())}")
        print(f"  SPI: {list(peripherals.get('spi', {}).get('ports', {}).keys())}")
        return 0
    
    elif subcmd in {"import", "scan"}:
        from tools.mcu.stm32_import import main as stm32_main
        return stm32_main(rest)
    
    else:
        print(f"未知子命令: {subcmd}")
        return 1


# ─── 项目设计 ────────────────────────────────────────────────────────────────

def cmd_design(argv: list[str]) -> int:
    """项目设计"""
    ensure_project_imports()
    print("提示: design 是旧兼容入口；新项目请使用 `python3 tools/efw.py project create <name> --chip ...`。")
    
    chip = None
    output = Path("project.json")
    
    i = 0
    while i < len(argv):
        if argv[i] == "--chip" and i + 1 < len(argv):
            chip = argv[i + 1]
            i += 2
        elif argv[i] in {"-o", "--output"} and i + 1 < len(argv):
            output = Path(argv[i + 1])
            i += 2
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("design")
            return 0
        else:
            i += 1
    
    if not chip:
        print("错误: 请指定芯片 (--chip)")
        print("用法: python3 tools/efw.py design --chip STM32F407VGT6 -o project.json")
        return 1
    
    from tools.simulator.chip_db import get_chip_database
    db = get_chip_database()
    chip_data = db.load_chip(chip)
    
    if not chip_data:
        print(f"未找到芯片: {chip}")
        return 1
    
    # 生成项目配置
    config = {
        "project": {
            "name": chip.lower().replace(" ", "_"),
            "chip": chip,
            "tick_ms": 1,
        },
        "board": {
            "profile": chip_data.get("board", ""),
            "pin_plan": [],
        },
        "nodes": [
            {
                "id": "app_module",
                "type": "project.module",
                "display_name": "应用模块",
                "description": f"{chip} 的默认应用模块。",
            }
        ],
        "edges": [],
        "flows": [],
        "tasks": [],
        "custom_files": [],
        "metadata": {
            "kind": "efw.graph",
            "schema_version": 1,
        },
        "chip_data": {
            "family": chip_data.get("family"),
            "core": chip_data.get("core"),
            "clock_mhz": chip_data.get("frequency_mhz"),
            "flash_kb": chip_data.get("flash_kb"),
            "ram_kb": chip_data.get("ram_kb"),
            "gpio_pins": chip_data.get("gpio_pins", []),
            "peripherals": chip_data.get("peripherals", {}),
        },
        # Legacy fields kept for older tools that consume design output directly.
        "name": chip.lower().replace(" ", "_"),
        "chip": chip,
        "family": chip_data.get("family"),
        "core": chip_data.get("core"),
        "clock_mhz": chip_data.get("frequency_mhz"),
        "flash_kb": chip_data.get("flash_kb"),
        "ram_kb": chip_data.get("ram_kb"),
        "gpio_pins": chip_data.get("gpio_pins", []),
        "peripherals": chip_data.get("peripherals", {}),
        "components": [],
        "tasks": [],
    }
    
    with open(output, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 项目配置已生成: {output}")
    print(f"  芯片: {chip}")
    print(f"  GPIO: {len(config['gpio_pins'])} 个")
    print(f"  ADC: {config['peripherals'].get('adc', {}).get('count', 0)} 通道")
    print(f"  PWM: {config['peripherals'].get('pwm', {}).get('count', 0)} 路")
    
    return 0


def resolve_graph_path(config_path: Path, config: dict[str, Any]) -> Path:
    """Resolve a graph JSON from a graph file, project file, or design output."""
    if "nodes" in config and "project" in config:
        return config_path

    graph_path = config.get("graph_path")
    if graph_path:
        path = Path(graph_path)
        if not path.is_absolute():
            path = config_path.parent / path
        return path

    raise ValueError("输入不是 Graph JSON，也没有 graph_path；请先运行 design 生成 graph 或直接传入 graph.json")


def run_codegen(graph_path: Path, output: Path, force: bool = True, dry_run: bool = False) -> int:
    ensure_project_imports()
    from codegen.cli import main as codegen_main

    args = [str(graph_path), "-o", str(output)]
    if force:
        args.append("--force")
    if dry_run:
        args.append("--dry-run")
    return codegen_main(args)


# ─── 代码生成 ────────────────────────────────────────────────────────────────

def cmd_develop(argv: list[str]) -> int:
    """代码生成"""
    print("提示: develop 是旧兼容入口；新项目请使用 `python3 tools/efw.py project generate <project>`。")
    config_path = None
    output = Path("application")
    integrate_fw = True  # 默认集成固件
    dry_run = False
    
    i = 0
    while i < len(argv):
        if not argv[i].startswith("-") and not config_path:
            config_path = Path(argv[i])
            i += 1
        elif argv[i] in {"-o", "--output"} and i + 1 < len(argv):
            output = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--no-firmware":
            integrate_fw = False
            i += 1
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("develop")
            return 0
        else:
            i += 1
    
    if not config_path:
        print("错误: 请指定配置文件")
        print("用法: python3 tools/efw.py develop project.json -o src/")
        return 1
    
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        return 1
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    try:
        graph_path = resolve_graph_path(config_path, config)
        return run_codegen(graph_path, output, force=True, dry_run=dry_run)
    except ValueError as exc:
        print(f"警告: {exc}")
        print("回退到旧版最小应用骨架生成。")
    
    output.mkdir(parents=True, exist_ok=True)
    
    chip = config.get("chip", "Unknown")
    clock = config.get("clock_mhz", 168)
    
    # 集成固件
    if integrate_fw:
        print(f"集成固件库...")
        try:
            ensure_project_imports()
            
            from tools.firmware.integrator import integrate_firmware
            
            generated = integrate_firmware(
                chip=chip,
                project_dir=output,
            )
            
            print(f"✓ 固件集成完成:")
            for name, path in generated.items():
                print(f"  {name}: {path}")
        except Exception as e:
            print(f"警告: 固件集成失败: {e}")
            print("继续生成应用代码...")
    
    # 生成 app_board_config.h
    board_config = f'''/**
 * @file    app_board_config.h
 * @brief   板级配置
 * @chip    {chip}
 * @clock   {clock} MHz
 */

#ifndef APP_BOARD_CONFIG_H
#define APP_BOARD_CONFIG_H

#define APP_SYSCLK_MHZ     {clock}
#define APP_HCLK_MHZ        {clock}
#define APP_PCLK1_MHZ       {clock / 4}
#define APP_PCLK2_MHZ       {clock / 2}
#define APP_TICK_MS          1

#define MOTOR_MAX_RPM        300
#define MOTOR_PWM_FREQ_HZ    1000

#define LINE_SENSOR_CHANNELS 5
#define LINE_THRESHOLD       0.5f

#define PID_KP               1.5f
#define PID_KI               0.3f
#define PID_KD               0.05f

#endif
'''
    (output / "app_board_config.h").write_text(board_config)
    
    # 生成 main.c
    main_c = f'''/**
 * @file    main.c
 * @brief   主程序
 * @chip    {chip}
 */

#include "efw/efw.h"
#include "app_board_config.h"

void app_init(void)
{{
    efw_init();
    
    /* TODO: 注册 HAL */
    /* TODO: 注册传感器 */
    /* TODO: 注册执行器 */
    /* TODO: 注册算法 */
}}

void app_loop_1ms(void)
{{
    /* TODO: 读取传感器 */
    /* TODO: 执行算法 */
    /* TODO: 输出执行器 */
}}

int main(void)
{{
    app_init();
    
    while (1)
    {{
        app_loop_1ms();
    }}
    
    return 0;
}}
'''
    (output / "main.c").write_text(main_c)
    
    print(f"✓ 代码已生成: {output}/")
    print(f"  芯片: {chip}")
    print(f"  文件: app_board_config.h, main.c")
    
    return 0


# ─── 仿真验证 ────────────────────────────────────────────────────────────────

def cmd_simulate(argv: list[str]) -> int:
    """仿真验证"""
    chip = None
    duration = 1000
    
    i = 0
    while i < len(argv):
        if argv[i] == "--chip" and i + 1 < len(argv):
            chip = argv[i + 1]
            i += 2
        elif argv[i] == "--duration" and i + 1 < len(argv):
            duration = int(argv[i + 1])
            i += 2
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("simulate")
            return 0
        else:
            i += 1
    
    if not chip:
        print("错误: 请指定芯片 (--chip)")
        return 1
    
    from tools.simulator.core import MCUSimulator
    from tools.simulator.perf import PerformanceMonitor
    
    print(f"启动仿真: {chip}")
    
    try:
        mcu = MCUSimulator.from_chip(chip)
    except Exception as e:
        print(f"错误: {e}")
        return 1
    
    print(f"  时钟: {mcu.clock.sysclk_hz / 1_000_000} MHz")
    print(f"  时长: {duration} ms")
    print()
    
    monitor = PerformanceMonitor()
    monitor.start()
    
    cycles_per_ms = mcu.clock.sysclk_hz // 1000
    start_time = time.time()
    
    for i in range(duration):
        monitor.begin_frame()
        mcu.tick(cycles_per_ms)
        monitor.end_frame(cycles=cycles_per_ms, instructions=cycles_per_ms)
        
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  进度: {i + 1}/{duration} ({elapsed:.1f}s)")
    
    elapsed = time.time() - start_time
    
    print()
    print("=" * 60)
    print("仿真报告")
    print("=" * 60)
    print(f"  仿真时长: {duration} ms")
    print(f"  实际耗时: {elapsed:.2f} s")
    print(f"  仿真速度: {duration / 1000 / elapsed:.2f}x")
    print(f"  总周期数: {monitor._total_cycles:,}")
    print("=" * 60)
    
    return 0


# ─── 在线调试 ────────────────────────────────────────────────────────────────

def cmd_debug(argv: list[str]) -> int:
    """在线调试"""
    if not argv:
        print_command_help("debug")
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd in {"help", "-h", "--help"}:
        print_command_help("debug")
        return 0
    
    port = None
    baud = 115200
    output = Path("debug_log.jsonl")
    duration = 10.0
    
    i = 0
    while i < len(rest):
        if rest[i] == "--port" and i + 1 < len(rest):
            port = rest[i + 1]
            i += 2
        elif rest[i] == "--baud" and i + 1 < len(rest):
            baud = int(rest[i + 1])
            i += 2
        elif rest[i] in {"-o", "--output"} and i + 1 < len(rest):
            output = Path(rest[i + 1])
            i += 2
        elif rest[i] == "--duration" and i + 1 < len(rest):
            duration = float(rest[i + 1])
            i += 2
        else:
            i += 1
    
    if not port:
        print("错误: 请指定串口 (--port)")
        return 1
    
    if subcmd == "snapshot":
        from debug.collector import DebugCollector
        
        print(f"连接 MCU: {port} @ {baud}")
        try:
            collector = DebugCollector(port=port, baud=baud)
            collector.connect()
        except Exception as e:
            print(f"连接失败: {e}")
            return 1
        
        print("✓ 连接成功")
        snapshot = collector.read_snapshot()
        
        print("\n快照数据:")
        print("-" * 60)
        for name, info in snapshot.get("params", {}).items():
            value = info.get("value")
            unit = info.get("unit", "")
            print(f"  {name}: {value} {unit}")
        
        collector.disconnect()
        return 0
    
    elif subcmd == "record":
        from debug.collector import DebugCollector
        from debug.recorder import DebugRecorder
        
        print(f"连接 MCU: {port} @ {baud}")
        try:
            collector = DebugCollector(port=port, baud=baud)
            collector.connect()
        except Exception as e:
            print(f"连接失败: {e}")
            return 1
        
        print("✓ 连接成功")
        
        recorder = DebugRecorder(output)
        recorder.start()
        
        print(f"录制数据: {duration}秒 -> {output}")
        print("按 Ctrl+C 停止")
        
        start = time.time()
        count = 0
        
        try:
            while time.time() - start < duration:
                snapshot = collector.read_snapshot()
                recorder.record(snapshot)
                count += 1
                
                if count % 10 == 0:
                    elapsed = time.time() - start
                    print(f"\r  进度: {elapsed:.1f}/{duration}s ({count} 条)", end="")
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        
        recorder.stop()
        collector.disconnect()
        
        print(f"\n✓ 录制完成: {count} 条记录")
        return 0
    
    elif subcmd == "analyze":
        if not output.exists():
            print(f"日志文件不存在: {output}")
            return 1
        
        from debug.analyzer import DebugAnalyzer
        
        analyzer = DebugAnalyzer(output)
        analyzer.print_summary()
        return 0
    
    else:
        print(f"未知子命令: {subcmd}")
        return 1


# ─── 烧录运行 ────────────────────────────────────────────────────────────────

def cmd_flash(argv: list[str]) -> int:
    """烧录固件"""
    bin_file = None
    port = None
    tool = "stlink"
    erase = False
    
    i = 0
    while i < len(argv):
        if argv[i] == "--bin" and i + 1 < len(argv):
            bin_file = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--port" and i + 1 < len(argv):
            port = argv[i + 1]
            i += 2
        elif argv[i] == "--tool" and i + 1 < len(argv):
            tool = argv[i + 1]
            i += 2
        elif argv[i] == "--erase":
            erase = True
            i += 1
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("flash")
            return 0
        else:
            i += 1
    
    if not bin_file:
        print("错误: 请指定固件文件 (--bin)")
        return 1
    
    if not bin_file.exists():
        print(f"固件文件不存在: {bin_file}")
        return 1
    
    print(f"烧录固件: {bin_file}")
    print(f"  工具: {tool}")
    print(f"  端口: {port or '自动检测'}")
    print()
    
    # 根据工具类型执行烧录
    if tool == "stlink":
        cmd = ["st-flash"]
        if erase:
            cmd.append("--reset")
        cmd.extend(["write", str(bin_file), "0x08000000"])
    elif tool == "jlink":
        cmd = ["JLinkExe"]
        if port:
            cmd.extend(["-device", "STM32F407VG", "-if", "SWD", "-speed", "4000"])
    elif tool == "openocd":
        cmd = ["openocd"]
        if port:
            cmd.extend(["-f", "interface/stlink.cfg", "-f", "target/stm32f4x.cfg"])
    else:
        print(f"不支持的烧录工具: {tool}")
        return 1
    
    print(f"执行: {' '.join(cmd)}")
    print()
    print("注意: 烧录功能需要安装对应的烧录工具")
    print("  - st-flash: https://github.com/stlink-org/stlink")
    print("  - JLinkExe: https://www.segger.com/downloads/jlink/")
    print("  - openocd: http://openocd.org/")
    
    return 0


# ─── 固件管理 ────────────────────────────────────────────────────────────────

def cmd_firmware(argv: list[str]) -> int:
    """固件管理"""
    ensure_project_imports()
    
    from tools.firmware.manager import cmd_firmware as firmware_cmd
    return firmware_cmd(argv)


# ─── 编译构建 ────────────────────────────────────────────────────────────────

def cmd_build(argv: list[str]) -> int:
    """编译构建"""
    ensure_project_imports()
    
    from tools.compiler.compiler import cmd_build as compiler_cmd
    return compiler_cmd(argv)


def cmd_hw(argv: list[str]) -> int:
    """硬件配置"""
    ensure_project_imports()
    
    from tools.hw.config import cmd_hw as hw_cmd
    return hw_cmd(argv)


def cmd_board(argv: list[str]) -> int:
    """Board/Profile management."""
    ensure_project_imports()
    from tools.board.cli import main as board_main
    return board_main(argv)


def cmd_svd(argv: list[str]) -> int:
    """SVD import/generation command."""
    ensure_project_imports()
    from tools.api.svd import run_svd
    return run_svd(argv)


def cmd_codegen(argv: list[str]) -> int:
    """Graph code generation."""
    ensure_project_imports()
    from codegen.cli import main as codegen_main
    return codegen_main(argv)


def cmd_studio(argv: list[str]) -> int:
    """Launch Studio."""
    if argv and argv[0] in {"help", "-h", "--help"}:
        print("用法: python3 tools/efw.py studio")
        print("启动 EFW Studio 图形工作台；需要 PyQt6 或 PyQt5。")
        return 0
    ensure_project_imports()
    from tools.studio.app import main as studio_main
    return studio_main()


def cmd_workflow(argv: list[str]) -> int:
    """Workflow command."""
    ensure_project_imports()
    from tools.workflow import cmd_workflow as workflow_cmd
    return workflow_cmd(argv)


def cmd_project(argv: list[str]) -> int:
    """Project management command."""
    ensure_project_imports()
    from tools.project import main as project_main
    return project_main(argv)


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    
    if not args or args[0] in {"help", "-h", "--help"}:
        if len(args) > 1:
            print_command_help(args[1])
        else:
            print_help()
        return 0
    
    command = args[0]
    rest = args[1:]
    
    handlers = {
        "mcu": cmd_mcu,
        "firmware": cmd_firmware,
        "board": cmd_board,
        "svd": cmd_svd,
        "project": cmd_project,
        "design": cmd_design,
        "develop": cmd_develop,
        "codegen": cmd_codegen,
        "build": cmd_build,
        "hw": cmd_hw,
        "studio": cmd_studio,
        "workflow": cmd_workflow,
        "simulate": cmd_simulate,
        "debug": cmd_debug,
        "flash": cmd_flash,
    }
    
    if command in handlers:
        return handlers[command](rest)
    
    print(f"未知命令: {command}")
    print("运行 'python3 tools/efw.py help' 查看帮助")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
