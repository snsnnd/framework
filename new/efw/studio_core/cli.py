"""命令行：与界面调用同一个服务。

  uv run python -m studio_core.cli new ./app --template thermostat
  uv run python -m studio_core.cli check ./app
  uv run python -m studio_core.cli generate ./app
  uv run python -m studio_core.cli run ./app --ms 5000 --fire overheat --set target=60
"""
from __future__ import annotations

import argparse
import json
import sys

from . import codegen, project
from .debug import ProcTransport, build_virtual
from .fsutil import ServiceError
from .service import Service


def cmd_run(args) -> int:
    root = project.project_root(args.path)
    state = project.open_project(args.path)
    info = project.analyze(args.path, state["model"])
    if not info["ok"]:
        print(json.dumps(info["diagnostics"], ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    transport = ProcTransport(build_virtual(root, state["model"]), root)
    last: dict = {}
    events: list = []

    def pump_until_idle() -> None:
        for line in transport.lines():
            if not line.startswith("{"):
                continue
            obj = json.loads(line)
            if obj.get("e") == "idle":
                return
            if obj.get("e") == "snap":
                last.clear(); last.update(obj)
            elif obj.get("e") in ("trans", "err"):
                events.append(obj)
    try:
        for item in args.set or []:
            transport.write("set " + item.replace("=", " ", 1))
        for name in args.fire or []:
            transport.write(f"fire {name}")
        transport.write(f"run {args.ms}")
        pump_until_idle()
    finally:
        transport.close()
    print(json.dumps({"snapshot": last, "events": events}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="efw", description="EFW Studio 命令行")
    sub = parser.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("path"); n.add_argument("--name"); n.add_argument("--template", default="thermostat")
    for name in ("check", "preview", "generate"):
        sub.add_parser(name).add_argument("path")
    r = sub.add_parser("run"); r.add_argument("path"); r.add_argument("--ms", type=int, default=2000)
    r.add_argument("--fire", action="append"); r.add_argument("--set", action="append", help="key=value，可重复")
    args = parser.parse_args()
    try:
        if args.cmd == "new":
            result = project.create_project(args.path, args.name or args.path.rstrip("/").split("/")[-1], args.template)
            print(f"已创建 {result['path']}")
            return 0
        if args.cmd == "run":
            return cmd_run(args)
        state = project.open_project(args.path)
        if args.cmd == "check":
            info = project.analyze(args.path, state["model"])
            for d in info["diagnostics"]:
                print(f"[{d['level']}] {d['at']}: {d['message']}" + (f"  → {d['hint']}" if d['hint'] else ""))
            print(f"内存估算 {info['memory']['total']} 字节；{'可生成' if info['ok'] else '有错误'}")
            return 0 if info["ok"] else 1
        proposed = project.preview(args.path, state["model"])
        if args.cmd == "preview" or proposed["blocked"]:
            for f in proposed["files"]:
                print(f"{f['status']:8} {f['path']}")
            if proposed["blocked"]:
                print(proposed["reason"], file=sys.stderr)
                return 1
            return 0
        result = project.commit(args.path, state["model"], proposed["token"])
        print(f"已写入 {result['output']}")
        return 0
    except (ServiceError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
