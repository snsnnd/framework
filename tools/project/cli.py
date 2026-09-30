"""CLI adapter for the EFW project subtool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.api import build as build_api
from tools.api import device as device_api
from tools.api import graph as graph_api
from tools.api import project as project_api


def create_project(args: argparse.Namespace) -> int:
    result = project_api.create_project(
        args.name,
        output_dir=args.output,
        board_profile=args.board or "stm32-basic",
        project_dir=args.dir,
        chip=args.chip or "",
        force=args.force,
    )
    descriptor_path = result["project_path"]
    graph_path = result["graph_path"]
    descriptor = result["descriptor"]
    print(f"✓ 项目已创建: {descriptor['name']}")
    print(f"  项目文件: {project_api.format_path(descriptor_path)}")
    print(f"  Graph: {project_api.format_path(graph_path)}")
    print(f"  输出目录: {descriptor['output_dir']}")
    return 0


def list_projects(_args: argparse.Namespace) -> int:
    projects = project_api.list_projects()
    if not projects:
        print("暂无 EFW 项目。")
        return 0
    print(f"EFW 项目 ({len(projects)} 个):")
    for project in projects:
        if not project.get("readable"):
            print(f"  ! {project['display_path']} (无法读取)")
            continue
        print(f"  {project.get('name', '-'):<24} {project['display_path']}")
        print(f"    board={project.get('board_profile', '-') or '-'} graph={project.get('graph_path', '-') or '-'}")
    return 0


def info_project(args: argparse.Namespace) -> int:
    info = project_api.project_info(args.project)
    print(f"项目: {info['name']}")
    print(f"  文件: {info['display_path']}")
    print(f"  Graph: {info['graph_display_path']} {'✓' if info['graph_exists'] else '✗'}")
    print(f"  输出: {info['output_display_path']}")
    print(f"  板卡: {info['board_profile']}")
    if info.get("chip"):
        print(f"  芯片: {info['chip']}")
    if info.get("notes"):
        print(f"  备注: {info['notes']}")
    return 0


def validate_project(args: argparse.Namespace) -> int:
    result = project_api.validate_project(args.project)
    project = result["project"]
    path = result["project_path"]
    print(f"✓ 项目校验通过: {project.get('name', path.stem)}")
    print(f"  Graph: {project_api.format_path(result['graph_path'])}")
    return 0


def generate_project(args: argparse.Namespace) -> int:
    return project_api.generate_project(args.project, output=args.output, force=args.force, dry_run=args.dry_run)


def debug_project(args: argparse.Namespace) -> int:
    result, stdout, stderr = graph_api.debug_graph(args.project, args.sections if args.sections else None)
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    return result


def delete_project(args: argparse.Namespace) -> int:
    result = project_api.delete_project(args.project, confirmed=args.yes)
    if not result.get("deleted"):
        print(f"将删除项目描述及其项目目录: {project_api.format_path(result['project_dir'])}")
        print("请重新执行并加 --yes 确认。")
        return 1
    print(f"✓ 项目已删除: {result['name']}")
    return 0


def recent_projects(_args: argparse.Namespace) -> int:
    recent = project_api.recent_projects()
    if not recent:
        print("暂无最近项目。")
        return 0
    print("最近项目:")
    for item in recent:
        print(f"  {'✓' if item['exists'] else '✗'} {item['path']}")
    return 0


def build_project(args: argparse.Namespace) -> int:
    return build_api.build_project(args.project, chip=args.chip, build_dir=args.dir, generate_first=args.generate)


def simulate_project(args: argparse.Namespace) -> int:
    return build_api.simulate_project(args.project, chip=args.chip, duration=args.duration)


def flash_project(args: argparse.Namespace) -> int:
    return build_api.flash_project(args.project, bin_file=args.bin, port=args.port, tool=args.tool, erase=args.erase)


def device_debug_project(args: argparse.Namespace) -> int:
    return device_api.run_device_action(args.project, args.action, port=args.port, baud=args.baud, output=args.output, log_file=args.log_file, interval=args.interval, max_count=args.max_count, analyze_action=args.analyze_action)


def set_project(args: argparse.Namespace) -> int:
    path = project_api.set_project_fields(args.project, name=args.name, chip=args.chip, board=args.board, graph=args.graph, output=args.output, notes=args.notes)
    print(f"✓ 项目已更新: {project_api.format_path(path)}")
    return 0


def rename_project(args: argparse.Namespace) -> int:
    project_api.rename_project(args.project, args.name)
    print(f"✓ 项目已重命名: {args.name}")
    return 0


def clone_project(args: argparse.Namespace) -> int:
    result = project_api.clone_project(
        args.project,
        args.name,
        output=args.output,
        board_profile=args.board,
        project_dir=args.dir,
        chip=args.chip,
        force=args.force,
    )
    descriptor_path = result["project_path"]
    graph_path = result["graph_path"]
    descriptor = result["descriptor"]
    print(f"✓ 项目已克隆: {descriptor['name']}")
    print(f"  项目文件: {project_api.format_path(descriptor_path)}")
    print(f"  Graph: {project_api.format_path(graph_path)}")
    return 0


def graph_project(args: argparse.Namespace) -> int:
    if args.graph_command == "info":
        info = graph_api.graph_info(args.project)
        print(f"Graph: {info['graph_path']}")
        print(f"  project: {info['project_name']}")
        print(f"  nodes: {info['nodes']}")
        print(f"  edges: {info['edges']}")
        print(f"  flows: {info['flows']}")
        print(f"  tasks: {info['tasks']}")
        print(f"  custom_files: {info['custom_files']}")
        return 0
    if args.graph_command == "path":
        print(project_api.format_path(graph_api.graph_path(args.project)))
        return 0
    if args.graph_command == "export":
        output = project_api.resolve_path(args.output)
        graph_api.export_graph(args.project, output)
        print(f"✓ Graph 已导出: {project_api.format_path(output)}")
        return 0
    if args.graph_command == "format":
        graph_path = graph_api.format_graph(args.project)
        print(f"✓ Graph 已格式化: {project_api.format_path(graph_path)}")
        return 0
    raise ValueError(f"未知 graph 命令: {args.graph_command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="efw project", description="Manage EFW projects.")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("create", help="create a project")
    p.add_argument("name")
    p.add_argument("--chip", default="")
    p.add_argument("--board", default="")
    p.add_argument("--dir")
    p.add_argument("-o", "--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=create_project)
    for name, func, help_text in [
        ("list", list_projects, "list known projects"),
        ("recent", recent_projects, "show recent projects"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
    for name, func, help_text in [
        ("info", info_project, "show project info"),
        ("validate", validate_project, "validate project graph"),
        ("delete", delete_project, "delete a managed project"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("project")
        if name == "delete":
            p.add_argument("--yes", action="store_true")
        p.set_defaults(func=func)
    p = sub.add_parser("generate", help="generate application from project graph")
    p.add_argument("project")
    p.add_argument("-o", "--output")
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=generate_project)
    p = sub.add_parser("debug", help="show runtime flow analysis for a project graph")
    p.add_argument("project")
    p.add_argument("--section", dest="sections", action="append", choices=["info", "init", "dataflow", "scheduler", "state", "events", "loop", "linefollower", "all"])
    p.set_defaults(func=debug_project)
    p = sub.add_parser("build", help="build a generated project application")
    p.add_argument("project")
    p.add_argument("--chip")
    p.add_argument("--dir")
    p.add_argument("--generate", action="store_true", help="run project generate before build")
    p.set_defaults(func=build_project)
    p = sub.add_parser("simulate", help="simulate the project target MCU")
    p.add_argument("project")
    p.add_argument("--chip")
    p.add_argument("--duration", type=int, default=1000)
    p.set_defaults(func=simulate_project)
    p = sub.add_parser("flash", help="flash a project firmware binary")
    p.add_argument("project")
    p.add_argument("--bin")
    p.add_argument("--port")
    p.add_argument("--tool", default="stlink")
    p.add_argument("--erase", action="store_true")
    p.set_defaults(func=flash_project)
    p = sub.add_parser("device", help="project-scoped real-device debug commands")
    p.add_argument("project")
    p.add_argument("action", choices=["ports", "snapshot", "schema", "list", "record", "analyze", "panel"])
    p.add_argument("--port")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("-o", "--output")
    p.add_argument("--log-file")
    p.add_argument("--interval", type=int)
    p.add_argument("--max-count", type=int)
    p.add_argument("--analyze-action", choices=["summary", "issues", "stats", "export", "anomalies"], default="summary")
    p.set_defaults(func=device_debug_project)
    p = sub.add_parser("set", help="edit project descriptor fields")
    p.add_argument("project")
    p.add_argument("--name")
    p.add_argument("--chip")
    p.add_argument("--board")
    p.add_argument("--graph")
    p.add_argument("--output")
    p.add_argument("--notes")
    p.set_defaults(func=set_project)
    p = sub.add_parser("rename", help="rename a project descriptor")
    p.add_argument("project")
    p.add_argument("name")
    p.set_defaults(func=rename_project)
    p = sub.add_parser("clone", help="clone a project descriptor and graph")
    p.add_argument("project")
    p.add_argument("name")
    p.add_argument("--chip")
    p.add_argument("--board")
    p.add_argument("--dir")
    p.add_argument("-o", "--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=clone_project)
    p = sub.add_parser("graph", help="inspect, export, or format a project graph")
    p.add_argument("project")
    graph_sub = p.add_subparsers(dest="graph_command")
    graph_sub.required = True
    graph_sub.add_parser("info", help="show graph summary")
    graph_sub.add_parser("path", help="print graph JSON path")
    gp = graph_sub.add_parser("export", help="export graph JSON")
    gp.add_argument("-o", "--output", required=True)
    graph_sub.add_parser("format", help="format graph JSON without semantic edits")
    p.set_defaults(func=graph_project)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"efw project: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
