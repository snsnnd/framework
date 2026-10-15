"""EFW 在线调试 CLI

提供命令行接口，用于连接 MCU、采集数据、比对分析、记录回放。

用法：
    python -m tools.debug.cli connect --port /dev/ttyUSB0
    python -m tools.debug.cli snapshot --port /dev/ttyUSB0
    python -m tools.debug.cli record --port /dev/ttyUSB0 -o debug.jsonl
    python -m tools.debug.cli analyze debug.jsonl --action summary
    python -m tools.debug.cli compare snapshot.json --expected expected.json
    python -m tools.debug.cli ports
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_ports(args: argparse.Namespace) -> int:
    """列出可用串口"""
    from tools.api import device as device_api

    ports = device_api.list_device_ports()
    
    if not ports:
        print("未找到串口设备")
        return 0
    
    print(f"找到 {len(ports)} 个串口:")
    for p in ports:
        print(f"  {p['device']:<20} {p['description']}")
    
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """读取单次快照"""
    try:
        from tools.api import device as device_api
        snapshot = device_api.snapshot_device(port=args.port, baud=args.baud)
        if args.pretty:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(snapshot, ensure_ascii=False))
        
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_schema(args: argparse.Namespace) -> int:
    """获取 MCU schema"""
    try:
        from tools.api import device as device_api
        schema = device_api.read_device_schema(port=args.port, baud=args.baud)
        if args.pretty:
            print(json.dumps(schema, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(schema, ensure_ascii=False))
        
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_list_points(args: argparse.Namespace) -> int:
    """列出调试监控点"""
    try:
        from tools.api import device as device_api
        points = device_api.read_debug_points(port=args.port, baud=args.baud)
        print(f"找到 {len(points)} 个调试监控点:")
        for p in points:
            print(f"  {p['name']:<30} type={p['type']:<8} id=0x{p['param_id']:04X}")
        
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """读取 EFW debug 模块统计"""
    try:
        from tools.api import device as device_api
        stats = device_api.read_debug_stats(port=args.port, baud=args.baud)
        if args.pretty:
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(stats, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_perf(args: argparse.Namespace) -> int:
    """读取 EFW debug/LiteTune 性能指标"""
    try:
        from tools.api import device as device_api
        perf = device_api.read_debug_perf(port=args.port, baud=args.baud)
        if args.pretty:
            print(json.dumps(perf, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(perf, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_record(args: argparse.Namespace) -> int:
    """持续记录数据"""
    try:
        from tools.api import device as device_api
        if args.expected:
            print(f"已加载预期配置: {args.expected}")
        print(f"开始记录到: {args.output}")
        print("按 Ctrl+C 停止记录...")
        stats = device_api.record_device_count(
            port=args.port,
            baud=args.baud,
            output=args.output,
            interval_ms=args.interval,
            max_count=args.max_count,
            expected=args.expected,
            verbose=args.verbose,
            show_issues=args.show_issues,
        )
        print("\n记录完成:")
        print(f"  快照数: {stats.get('total_snapshots', stats.get('sample_count', 0))}")
        print(f"  问题数: {stats.get('total_issues', 0)}")
        print(f"  输出文件: {args.output}")
        return 0
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_compare(args: argparse.Namespace) -> int:
    """比对快照数据"""
    from .comparator import DebugComparator
    
    try:
        # 加载快照
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        
        # 加载预期配置
        comparator = DebugComparator.from_file(args.expected)
        
        # 执行比对
        result = comparator.compare(snapshot)
        
        if args.pretty:
            print(comparator.format_report(result))
        else:
            print(json.dumps(result.to_dict(), ensure_ascii=False))
        
        return 1 if result.error_count > 0 else 0
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_analyze(args: argparse.Namespace) -> int:
    """分析记录文件"""
    try:
        from tools.api import device as device_api
        result = device_api.analyze_recording(args.log_file, action=args.action, param=args.param, output=args.output, limit=args.limit)
        if args.action in {"issues", "anomalies"}:
            for item in result:
                print(json.dumps(item, ensure_ascii=False))
        elif args.action == "stats":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.action == "export":
            print(f"已导出到: {result['output']}")
        
        return 0
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_panel(args: argparse.Namespace) -> int:
    """启动 PyQt 调试面板"""
    try:
        from .panel import main as panel_main
        return panel_main()
    except ImportError as e:
        print(f"错误: {e}", file=sys.stderr)
        print("PyQt 面板需要 PyQt6，请安装: pip install PyQt6", file=sys.stderr)
        return 1


def cmd_transport_template(args: argparse.Namespace) -> int:
    """安装调试协议传输适配模板"""
    try:
        from tools.api import device as device_api
        result = device_api.install_debug_transport_template(args.output, protocol=args.protocol, transport=args.transport, force=args.force)
        print(f"已生成 {result.protocol}({result.transport}) 传输适配文件: {result.output}")
        print("只需要修改其中的 app_debug_transport_write_bytes() 绑定 UART/USB CDC。")
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器"""
    parser = argparse.ArgumentParser(
        prog="efw-debug",
        description="EFW 在线调试工具",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # ports 命令
    p = subparsers.add_parser("ports", help="列出可用串口")
    p.set_defaults(func=cmd_ports)
    
    # snapshot 命令
    p = subparsers.add_parser("snapshot", help="读取单次快照")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.add_argument("--pretty", action="store_true", help="美化输出")
    p.set_defaults(func=cmd_snapshot)
    
    # schema 命令
    p = subparsers.add_parser("schema", help="获取 MCU schema")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.add_argument("--pretty", action="store_true", help="美化输出")
    p.set_defaults(func=cmd_schema)
    
    # list 命令
    p = subparsers.add_parser("list", help="列出调试监控点")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.set_defaults(func=cmd_list_points)

    # stats 命令
    p = subparsers.add_parser("stats", help="读取 EFW debug 模块统计")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.add_argument("--pretty", action="store_true", help="美化输出")
    p.set_defaults(func=cmd_stats)

    # perf 命令
    p = subparsers.add_parser("perf", help="读取 EFW debug/LiteTune 性能指标")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.add_argument("--pretty", action="store_true", help="美化输出")
    p.set_defaults(func=cmd_perf)
    
    # record 命令
    p = subparsers.add_parser("record", help="持续记录数据")
    p.add_argument("--port", required=True, help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.add_argument("-o", "--output", required=True, help="输出文件路径")
    p.add_argument("--expected", help="预期配置文件路径")
    p.add_argument("--interval", type=int, default=100, help="采集间隔（毫秒）")
    p.add_argument("--max-count", type=int, help="最大采集次数")
    p.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    p.add_argument("--show-issues", action="store_true", help="显示问题详情")
    p.set_defaults(func=cmd_record)
    
    # compare 命令
    p = subparsers.add_parser("compare", help="比对快照数据")
    p.add_argument("snapshot", help="快照文件路径")
    p.add_argument("--expected", required=True, help="预期配置文件路径")
    p.add_argument("--pretty", action="store_true", help="美化输出")
    p.set_defaults(func=cmd_compare)
    
    # analyze 命令
    p = subparsers.add_parser("analyze", help="分析记录文件")
    p.add_argument("log_file", help="日志文件路径")
    p.add_argument("--action", choices=["summary", "issues", "stats", "export", "anomalies"],
                  default="summary", help="操作类型")
    p.add_argument("--param", help="参数名称")
    p.add_argument("-o", "--output", help="输出文件路径")
    p.add_argument("--limit", type=int, default=100, help="限制输出数量")
    p.set_defaults(func=cmd_analyze)
    
    # panel 命令
    p = subparsers.add_parser("panel", help="启动 PyQt 调试面板")
    p.add_argument("--port", help="串口设备路径")
    p.add_argument("--baud", type=int, default=115200, help="波特率")
    p.set_defaults(func=cmd_panel)

    # transport-template 命令
    p = subparsers.add_parser("transport-template", help="生成调试协议传输适配模板")
    p.add_argument("protocol", nargs="?", default="litetune", choices=["litetune"], help="调试协议")
    p.add_argument("--transport", default="uart", choices=["uart", "usb-cdc"], help="承载传输")
    p.add_argument("-o", "--output", default="board_adapters/efw_litetune_transport_port.c", help="输出路径")
    p.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p.set_defaults(func=cmd_transport_template)
    
    return parser


def main(argv: list[str] | None = None) -> int:
    """主入口"""
    parser = build_parser()
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
