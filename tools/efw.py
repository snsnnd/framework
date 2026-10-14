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
import subprocess
import sys
from pathlib import Path


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
  transport-template  生成调试协议传输适配模板

选项:
  --port PORT         串口设备（如 /dev/ttyUSB0 或 COM3）
  --baud BAUD         波特率（默认 115200）
  -o, --output FILE   输出文件
  --duration SEC      录制时长（秒）

示例:
  python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
  python3 tools/efw.py debug record --port /dev/ttyUSB0 -o log.jsonl --duration 60
  python3 tools/efw.py debug transport-template litetune --transport uart -o board_adapters/efw_litetune_transport_port.c""",
        
        "flash": """用法: python3 tools/efw.py flash [options]

烧录固件到 MCU。

选项:
  --bin FILE          固件文件路径
  --chip CHIP         目标芯片（如 STM32F407VGT6）
  --port PORT         串口/调试器端口
  --tool TOOL         烧录工具（stlink, jlink, openocd）
  --erase             烧录前擦除
  --dry-run           仅显示命令，不执行烧录

示例:
  python3 tools/efw.py flash --bin build/app.bin --chip STM32F407VGT6 --port COM3 --tool stlink""",
        
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
    
    from tools.api.legacy import design_graph_for_chip

    try:
        config = design_graph_for_chip(chip, output)
    except Exception as exc:
        print(f"错误: {exc}")
        return 1
    
    print(f"✓ 项目配置已生成: {output}")
    print(f"  芯片: {chip}")
    print(f"  GPIO: {len(config['gpio_pins'])} 个")
    print(f"  ADC: {config['peripherals'].get('adc', {}).get('count', 0)} 通道")
    print(f"  PWM: {config['peripherals'].get('pwm', {}).get('count', 0)} 路")
    
    return 0


# ─── 代码生成 ────────────────────────────────────────────────────────────────

def cmd_develop(argv: list[str]) -> int:
    """代码生成"""
    ensure_project_imports()
    print("提示: develop 是旧兼容入口；新项目请使用 `python3 tools/efw.py project generate <project>`。")
    config_path = None
    output = Path("application")
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

    try:
        from tools.api.legacy import generate_from_config
        return generate_from_config(config_path, output, force=True, dry_run=dry_run)
    except Exception as exc:
        print(f"错误: {exc}")
        return 1


# ─── 仿真验证 ────────────────────────────────────────────────────────────────

def cmd_simulate(argv: list[str]) -> int:
    """仿真验证"""
    ensure_project_imports()
    chip = None
    duration = 1000
    workload = "idle"

    i = 0
    while i < len(argv):
        if argv[i] == "--chip" and i + 1 < len(argv):
            chip = argv[i + 1]
            i += 2
        elif argv[i] == "--duration" and i + 1 < len(argv):
            duration = int(argv[i + 1])
            i += 2
        elif argv[i] == "--workload" and i + 1 < len(argv):
            workload = argv[i + 1]
            i += 2
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("simulate")
            return 0
        else:
            i += 1

    if not chip:
        print("错误: 请指定芯片 (--chip)")
        return 1

    print(f"启动仿真: {chip} (workload={workload})")

    try:
        from tools.api.legacy import simulate_chip
        report = simulate_chip(chip, duration=duration, workload=workload)
    except Exception as e:
        print(f"错误: {e}")
        return 1

    if report.get("workload") == "efw":
        # calibrated model report already printed its details
        print("=" * 60)
        print("EFW 校准仿真报告（实机测量校准）")
        print("=" * 60)
        print(f"  1ms tick 框架开销: {report['cycles_per_tick']} / {report['capacity_cycles_per_tick']} cycles")
        print(f"  CPU 利用率: {report['utilization']*100:.1f}%   余量: {report['headroom_pct']:.1f}%")
        print("=" * 60)
        return 0

    print(f"  时钟: {report['sysclk_hz'] / 1_000_000} MHz")
    print(f"  时长: {duration} ms")
    print()

    print()
    print("=" * 60)
    print("仿真报告")
    print("=" * 60)
    print(f"  仿真时长: {report['duration_ms']} ms")
    print(f"  实际耗时: {report['elapsed_seconds']:.2f} s")
    print(f"  仿真速度: {report['speed_x']:.2f}x")
    print(f"  总周期数: {report['total_cycles']:,}")
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

    if subcmd == "transport-template":
        protocol = "litetune"
        transport = "uart"
        output_path = Path("board_adapters/efw_litetune_transport_port.c")
        force = False
        i = 0
        if rest and not rest[0].startswith("-"):
            protocol = rest[0]
            i = 1
        while i < len(rest):
            if rest[i] in {"-o", "--output"} and i + 1 < len(rest):
                output_path = Path(rest[i + 1])
                i += 2
            elif rest[i] == "--transport" and i + 1 < len(rest):
                transport = rest[i + 1]
                i += 2
            elif rest[i] == "--force":
                force = True
                i += 1
            else:
                i += 1
        try:
            from tools.api import device as device_api
            result = device_api.install_debug_transport_template(output_path, protocol=protocol, transport=transport, force=force)
        except Exception as e:
            print(f"错误: {e}")
            return 1
        print(f"已生成 {result.protocol}({result.transport}) 传输适配文件: {result.output}")
        print("只需要修改其中的 app_debug_transport_write_bytes() 绑定 UART/USB CDC。")
        return 0

    if subcmd == "protocol":
        action = rest[0] if rest else "show"
        from tools.api import groundstation as groundstation_api
        try:
            if action == "init":
                path = Path(rest[1]) if len(rest) > 1 else Path("efw_protocol_profile.json")
                force = "--force" in rest[2:]
                output = groundstation_api.init_profile(path, force=force)
                print(f"已生成协议 profile: {output}")
                print("可在项目 .efw_project.json 中设置 protocol_profile 指向该文件。")
                return 0
            if action == "show":
                path = rest[1] if len(rest) > 1 else None
                profile = groundstation_api.load_profile(path)
                print(json.dumps(profile, indent=2, ensure_ascii=False))
                return 0
        except Exception as e:
            print(f"错误: {e}")
            return 1
        print(f"未知 protocol 子命令: {action}")
        return 1
    
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
        print(f"连接 MCU: {port} @ {baud}")
        try:
            from tools.api import device as device_api
            snapshot = device_api.snapshot_device(port=port, baud=baud)
        except Exception as e:
            print(f"连接失败: {e}")
            return 1
        
        print("✓ 连接成功")
        
        print("\n快照数据:")
        print("-" * 60)
        for name, info in snapshot.get("params", {}).items():
            value = info.get("value")
            unit = info.get("unit", "")
            print(f"  {name}: {value} {unit}")
        
        return 0

    if subcmd == "perf":
        print(f"连接 MCU: {port} @ {baud}")
        try:
            from tools.api import device as device_api
            perf = device_api.read_debug_perf(port=port, baud=baud)
        except Exception as e:
            print(f"连接失败: {e}")
            return 1
        print(json.dumps(perf, indent=2, ensure_ascii=False))
        return 0
    
    elif subcmd == "record":
        print(f"连接 MCU: {port} @ {baud}")
        try:
            from tools.api import device as device_api
            print("✓ 连接成功")
            print(f"录制数据: {duration}秒 -> {output}")
            stats = device_api.record_device(port=port, baud=baud, output=output, duration=duration)
        except Exception as e:
            print(f"连接失败: {e}")
            return 1
        print(f"✓ 录制完成: {stats.get('sample_count', 0)} 条记录")
        return 0
    
    elif subcmd == "analyze":
        if not output.exists():
            print(f"日志文件不存在: {output}")
            return 1
        
        from tools.api import device as device_api
        device_api.analyze_recording(output)
        return 0
    
    else:
        print(f"未知子命令: {subcmd}")
        return 1


# ─── 烧录运行 ────────────────────────────────────────────────────────────────

def cmd_flash(argv: list[str]) -> int:
    """烧录固件"""
    ensure_project_imports()
    bin_file = None
    chip = None
    port = None
    tool = None
    erase = False
    dry_run = False
    
    i = 0
    while i < len(argv):
        if argv[i] == "--bin" and i + 1 < len(argv):
            bin_file = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--chip" and i + 1 < len(argv):
            chip = argv[i + 1]
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
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] in {"help", "-h", "--help"}:
            print_command_help("flash")
            return 0
        else:
            print(f"错误: 未知烧录参数: {argv[i]}")
            return 1
    
    if not bin_file:
        print("错误: 请指定固件文件 (--bin)")
        return 1
    
    print(f"烧录固件: {bin_file}")
    print(f"  工具: {tool or '目标默认'}")
    print(f"  端口: {port or '自动检测'}")
    print()
    
    try:
        from tools.api.flash import run_flash
        cmd = run_flash(bin_file, chip=chip, tool=tool, port=port, erase=erase, dry_run=dry_run)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        return 1
    except ValueError as exc:
        print(f"错误: {exc}")
        return 1
    except OSError as exc:
        print(f"错误: 无法启动烧录工具: {exc}")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"错误: 烧录工具退出码 {exc.returncode}")
        return exc.returncode or 1
    except Exception as exc:
        print(f"错误: {exc}")
        return 1
    
    print(f"{'计划' if dry_run else '已执行'}: {' '.join(cmd)}")
    print()
    if dry_run:
        print("dry-run: 未执行烧录")
    
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
