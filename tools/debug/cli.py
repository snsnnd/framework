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
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def cmd_ports(args: argparse.Namespace) -> int:
    """列出可用串口"""
    from .collector import list_serial_ports
    
    ports = list_serial_ports()
    
    if not ports:
        print("未找到串口设备")
        return 0
    
    print(f"找到 {len(ports)} 个串口:")
    for p in ports:
        print(f"  {p['device']:<20} {p['description']}")
    
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """读取单次快照"""
    from .collector import DebugCollector
    
    try:
        with DebugCollector(port=args.port, baud=args.baud) as collector:
            snapshot = collector.read_snapshot()
            
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
    from .collector import DebugCollector
    
    try:
        with DebugCollector(port=args.port, baud=args.baud) as collector:
            schema = collector.get_schema()
            
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
    from .collector import DebugCollector
    
    try:
        with DebugCollector(port=args.port, baud=args.baud) as collector:
            points = collector.read_debug_points()
            
            print(f"找到 {len(points)} 个调试监控点:")
            for p in points:
                print(f"  {p['name']:<30} type={p['type']:<8} id=0x{p['param_id']:04X}")
        
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_record(args: argparse.Namespace) -> int:
    """持续记录数据"""
    from .collector import DebugCollector
    from .comparator import DebugComparator
    from .recorder import RecordingSession
    
    try:
        # 创建采集器
        collector = DebugCollector(port=args.port, baud=args.baud)
        collector.connect()
        
        # 创建比对器（如果指定了预期配置）
        comparator = None
        if args.expected:
            comparator = DebugComparator.from_file(args.expected)
            print(f"已加载预期配置: {args.expected}")
        
        # 创建记录会话
        with RecordingSession(
            args.output,
            comparator=comparator,
            auto_compare=bool(comparator),
        ) as session:
            print(f"开始记录到: {args.output}")
            print("按 Ctrl+C 停止记录...")
            
            # 设置信号处理
            stop = False
            def signal_handler(sig, frame):
                nonlocal stop
                stop = True
            
            signal.signal(signal.SIGINT, signal_handler)
            
            # 记录循环
            interval = args.interval / 1000.0
            count = 0
            
            while not stop:
                try:
                    snapshot = collector.read_snapshot()
                    issues = session.process(snapshot)
                    count += 1
                    
                    # 实时显示
                    if args.verbose:
                        params = snapshot.get("params", {})
                        print(f"[{count}] {len(params)} params", end="")
                        if issues:
                            print(f", {len(issues)} issues", end="")
                        print()
                    
                    if issues and args.show_issues:
                        for issue in issues:
                            print(f"  ⚠ {issue['name']}: {issue['detail']}")
                    
                    time.sleep(interval)
                    
                    # 检查最大数量
                    if args.max_count and count >= args.max_count:
                        break
                
                except Exception as e:
                    print(f"采集错误: {e}", file=sys.stderr)
                    time.sleep(1)
            
            # 停止并显示统计
            stats = session.stop()
            print(f"\n记录完成:")
            print(f"  快照数: {stats.get('total_snapshots', 0)}")
            print(f"  问题数: {stats.get('total_issues', 0)}")
            print(f"  输出文件: {args.output}")
        
        collector.disconnect()
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
    from .analyzer import DebugAnalyzer
    
    try:
        analyzer = DebugAnalyzer(args.log_file)
        
        if args.action == "summary":
            analyzer.print_summary()
        
        elif args.action == "issues":
            issues = analyzer.find_all_issues()
            if args.param:
                issues = [i for i in issues if i.get("name") == args.param]
            
            for issue in issues[:args.limit]:
                print(json.dumps(issue, ensure_ascii=False))
        
        elif args.action == "stats":
            if args.param:
                stats = analyzer.get_param_stats(args.param)
            else:
                stats = analyzer.get_all_param_stats()
            
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        elif args.action == "export":
            if not args.output:
                print("导出操作需要 --output 参数", file=sys.stderr)
                return 1
            
            analyzer.export_csv(args.output, params=[args.param] if args.param else None)
            print(f"已导出到: {args.output}")
        
        elif args.action == "anomalies":
            if not args.param:
                print("异常检测需要 --param 参数", file=sys.stderr)
                return 1
            
            anomalies = analyzer.find_anomalies(args.param)
            for a in anomalies[:args.limit]:
                print(json.dumps(a, ensure_ascii=False))
        
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
