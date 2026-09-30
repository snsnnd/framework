"""Board profile command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.api import board as board_api
from tools.project.core import display_path


def list_boards(_args: argparse.Namespace) -> int:
    profiles = board_api.list_profiles()
    print(f"Board Profiles ({len(profiles)}):")
    for name in sorted(profiles):
        profile = profiles[name]
        label = profile.get("label") or profile.get("mcu") or ""
        mcu = profile.get("mcu") or ""
        print(f"  {name:<28} {label} {f'({mcu})' if mcu else ''}")
    return 0


def info_board(args: argparse.Namespace) -> int:
    profile = board_api.get_profile(args.profile)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def import_board(args: argparse.Namespace) -> int:
    out_path = board_api.import_profile(args.file, name=args.name, output_dir=args.output_dir or "data/board_profiles")
    print(f"✓ Board Profile 已导入: {display_path(out_path)}")
    return 0


def set_project_board(args: argparse.Namespace) -> int:
    path = board_api.set_project_profile(args.project, args.profile)
    print(f"✓ 项目 Board Profile 已设置: {args.profile}")
    print(f"  项目: {display_path(path)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="efw board", description="Manage EFW board profiles.")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("list", help="list board profiles")
    p.set_defaults(func=list_boards)
    p = sub.add_parser("info", help="show a board profile")
    p.add_argument("profile")
    p.set_defaults(func=info_board)
    p = sub.add_parser("import", help="import a board profile JSON")
    p.add_argument("file")
    p.add_argument("--name")
    p.add_argument("--output-dir")
    p.set_defaults(func=import_board)
    p = sub.add_parser("set", help="set a project's board profile")
    p.add_argument("project")
    p.add_argument("profile")
    p.set_defaults(func=set_project_board)
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
        print(f"efw board: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
