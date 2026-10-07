"""把 EFW 暴露成 MCP 工具（stdio），让 agent 直接检测与控制。

    uv run --group agent python -m studio_core.mcp [项目路径]

设计取舍：
- **默认只读**。写操作（启动会话、改参数、触发事件、强制输出、生成代码）必须显式
  `--allow-write`，而且目标默认只允许虚拟目标（`--allow-targets`）。
- 真机（串口/TCP）上的写操作要再显式列出该目标，且每次写都记进 `.efw/agent-audit.jsonl`。
- 读操作也很有用：分析、manifest、录制回放——agent 不接板子也能"看"。
- stdout 只出 MCP 协议，所有日志走 stderr。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import project as project_mod
from .fsutil import ServiceError
from .model import analyze as analyze_model, model_hash
from .service import Service

WRITE = "write"
READ = "read"


def _schema(props: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


STR = {"type": "string"}
BOOL = {"type": "boolean"}
NUM = {"type": "number"}


class Policy:
    """写权限与审计。默认什么都不许写。"""

    def __init__(self, allow_write: bool, targets: list[str], root: Path | None):
        self.allow_write = allow_write
        self.targets = targets
        self.audit_file = (root / ".efw" / "agent-audit.jsonl") if root else None

    def check(self, tool: str, args: dict[str, Any]) -> None:
        if not self.allow_write:
            raise ServiceError("FORBIDDEN", f"{tool} 是写操作；请用 --allow-write 显式授权后再用")
        target = args.get("target")
        if isinstance(target, str):
            try:
                target = json.loads(target)
            except json.JSONDecodeError:
                pass
        if isinstance(target, dict):
            target = target.get("kind")
        target = target or args.get("kind")
        if target and target not in self.targets:
            raise ServiceError("FORBIDDEN", f"目标 {target} 不在允许列表 {self.targets}；真机上写操作要显式 --allow-targets")

    def record(self, tool: str, args: dict[str, Any], ok: bool, detail: str = "") -> None:
        if not self.audit_file:
            return
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": tool, "ok": ok, "detail": detail,
                 "args": {k: v for k, v in args.items() if k in {"path", "session", "key", "value", "event", "input", "target"}}}
        try:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass


READ_TOOLS: list[tuple[str, str, str, dict[str, Any]]] = [
    ("efw_open_project", "打开项目并返回它的结构概览（信号、输入输出、事件、数据流、状态机）",
     "读项目", _schema({"path": {**STR, "description": "项目目录的绝对路径"}})),
    ("efw_analyze", "跑模型分析：诊断、执行计划、内存估算、引用关系",
     "读项目", _schema({"path": STR}, ["path"])),
    ("efw_manifest", "读 manifest：固件对外暴露的信号、可整定参数、事件与输入输出",
     "读项目", _schema({"path": STR}, ["path"])),
    ("efw_sources", "列出或读取项目里的源文件（src/ 与 board/，用户所有）",
     "读源码", _schema({"path": STR, "file": {**STR, "description": "省略则只列文件名"}}, ["path"])),
    ("efw_runs", "列出 .efw/runs/ 下已录制的调试记录",
     "读录制", _schema({"path": STR}, ["path"])),
    ("efw_replay", "回放一段录制，返回帧（快照/事件/转换），可用于离线分析",
     "读录制", _schema({"path": STR, "run": {**STR, "description": "记录文件名"}, "limit": {**NUM, "description": "最多返回多少帧，默认 200"}}, ["path", "run"])),
    ("efw_state", "取一次完整状态：优先返回本进程里正在运行的会话，否则返回最近一次录制的末帧",
     "读状态", _schema({"path": STR, "session": {**STR, "description": "可选，指定会话"}}, ["path"])),
]

WRITE_TOOLS: list[tuple[str, str, str, dict[str, Any]]] = [
    ("efw_start", "启动一个调试会话（虚拟目标 / 串口 / TCP / 回放），会开始录制",
     "控制", _schema({"path": STR, "target": {**STR, "description": 'JSON，如 {"kind":"virtual"} 或 {"kind":"serial","port":"/dev/ttyUSB0","baud":115200}'}}, ["path", "target"])),
    ("efw_set", "整定一个可调参数或可整定信号（对应协议里的 set 命令）",
     "控制", _schema({"session": STR, "key": {**STR, "description": "参数名或信号 id"}, "value": NUM}, ["session", "key", "value"])),
    ("efw_fire", "触发一个事件",
     "控制", _schema({"session": STR, "event": STR}, ["session", "event"])),
    ("efw_force", "强制一个输入的值",
     "控制", _schema({"session": STR, "input": STR, "value": NUM}, ["session", "input", "value"])),
    ("efw_release", "释放被强制覆盖的输入",
     "控制", _schema({"session": STR, "input": STR}, ["session", "input"])),
    ("efw_stop", "停止会话（录制会落盘）",
     "控制", _schema({"session": STR}, ["session"])),
    ("efw_command", "遥控台：把一条文本命令原样发给目标（dump/rate/set/fire/force/release/push/pause/resume/state），"
     "人工在界面遥控台里用的是同一套命令",
     "控制", _schema({"session": STR, "line": {**STR, "description": "例如 dump、rate 200、set target 70、fire overheat、pause control"}}, ["session", "line"])),
    ("efw_generate", "预览或提交生成代码；commit=true 时才写盘",
     "写文件", _schema({"path": STR, "commit": {**BOOL, "description": "默认只预览"}}, ["path"])),
]


def summarize(opened: dict[str, Any]) -> dict[str, Any]:
    m = opened["model"]
    return {
        "path": opened["path"], "name": m["name"], "revision": opened["revision"],
        "tick_ms": m["tick_ms"],
        "signals": [{"id": s["id"], "label": s["label"], "type": s["type"], "unit": s["unit"],
                     "tunable": bool(s.get("tune"))} for s in m["signals"]],
        "inputs": [{"id": x["id"], "label": x["label"], "type": x["type"]} for x in m["inputs"]],
        "outputs": [{"id": x["id"], "label": x["label"], "type": x["type"]} for x in m["outputs"]],
        "events": [{"id": e["id"], "label": e["label"]} for e in m["events"]],
        "queues": [{"id": q["id"], "label": q["label"], "capacity": q["capacity"]} for q in m["queues"]],
        "flows": [{"id": f["id"], "label": f["label"], "period_ms": f["period_ms"], "steps": len(f["steps"])} for f in m["flows"]],
        "machines": [{"id": mc["id"], "label": mc["label"], "initial": mc["initial"],
                      "states": [{"id": s["id"], "label": s["label"], "run": s["run"]} for s in mc["states"]]}
                     for mc in m["machines"]],
    }


def run_tool(policy: Policy, service: Service, name: str, args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path")
    if name == "efw_open_project":
        return summarize(project_mod.open_project(path))
    if name == "efw_analyze":
        opened = project_mod.open_project(path)
        info = analyze_model(opened["model"], {})
        return {"ok": info["ok"], "hash": info["hash"], "diagnostics": info["diagnostics"],
                "plan": info["plan"], "memory": info["memory"]}
    if name == "efw_manifest":
        from . import codegen
        opened = project_mod.open_project(path)
        return json.loads(codegen.gen_manifest(opened["model"]))
    if name == "efw_sources":
        opened = project_mod.open_project(path)
        files = [f for f in opened["files"] if f.endswith((".c", ".h"))]
        if not args.get("file"):
            return {"files": files, "note": "src/ 与 board/ 永远归用户所有，工具不覆盖"}
        if args["file"] not in files:
            raise ServiceError("INVALID", f"不是项目里的源文件：{args['file']}")
        return {"file": args["file"], "content": project_mod.read_file(path, args["file"])["content"]}
    if name == "efw_runs":
        from .debug import list_runs
        return {"runs": list_runs(Path(path))}
    if name == "efw_replay":
        from .debug import ReplaySession
        limit = int(args.get("limit") or 200)
        sid = "agent-replay"
        frames: list[dict] = []
        done = threading_event(sid, Path(path), args["run"], limit, frames)
        return {"frames": frames, "ended": done}
    if name == "efw_state":
        return service.agent_state(path, args.get("session"))
    # ---- 写操作 ----
    if name == "efw_start":
        target = args["target"]
        if isinstance(target, str):
            target = json.loads(target)
        started = service.dispatch("debug.start", {"path": path, "target": target})
        return {"session": started["session"], "kind": started["kind"], "state": started["state"],
                "hash": started["manifest"]["hash"]}
    if name == "efw_set":
        service.dispatch("debug.send", {"session": args["session"], "line": f"set {args['key']} {args['value']}"})
        return {"ok": True}
    if name == "efw_fire":
        service.dispatch("debug.send", {"session": args["session"], "line": f"fire {args['event']}"})
        return {"ok": True}
    if name == "efw_force":
        service.dispatch("debug.send", {"session": args["session"], "line": f"force {args['input']} {args['value']}"})
        return {"ok": True}
    if name == "efw_release":
        service.dispatch("debug.send", {"session": args["session"], "line": f"release {args['input']}"})
        return {"ok": True}
    if name == "efw_command":
        from .debug import valid_command
        line = valid_command(args["line"])
        service.dispatch("debug.send", {"session": args["session"], "line": line})
        return {"sent": line, "note": "命令已发给目标；结果会出现在下一次 efw_state 或录制里"}
    if name == "efw_stop":
        return {"stopped": service.dispatch("debug.stop", {"session": args["session"]})}
    if name == "efw_generate":
        opened = project_mod.open_project(path)
        preview = project_mod.preview(path, opened["model"])
        if not args.get("commit"):
            return {"committed": False, "token": preview["token"], "blocked": preview["blocked"],
                    "reason": preview.get("reason", ""),
                    "files": [{"path": f["path"], "status": f["status"]} for f in preview["files"]]}
        result = project_mod.commit(path, opened["model"], preview["token"])
        return {"committed": True, "output": result["output"],
                "files": [{"path": f["path"], "status": f["status"]} for f in result["files"]]}
    raise ServiceError("INVALID", f"未知工具：{name}")


def threading_event(sid: str, root: Path, run: str, limit: int, out: list[dict]) -> bool:
    """回放到结束（或到达 limit）：直接读 jsonl，不起会话。"""
    from .fsutil import safe_path
    file = safe_path(root, f".efw/runs/{run}")
    try:
        with file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(out) >= limit:
                    break
    except OSError as exc:
        raise ServiceError("INVALID", f"读不了录制 {run}：{exc}") from exc
    return True


def _make_handler(name: str, schema: dict[str, Any]):
    """按 schema 生成显式参数的工具函数。

    不能用 **kwargs：MCP 2.x 用函数签名生成 input schema，kwargs 会被当成一个
    叫 "kwargs" 的必填字段。
    """
    props: dict[str, Any] = schema.get("properties", {})
    required = list(schema.get("required", []))
    optional = [k for k in props if k not in required]
    # Python 要求无默认值的参数在前：必填在前，可选在后
    args = [k for k in required] + [f"{k}={props[k].get('default')!r}" for k in optional]
    body = "    return await dispatch(_name, locals())"
    src = f"async def _tool({', '.join(args)}):\n{body}"
    namespace: dict[str, Any] = {"dispatch": None, "_name": name}
    exec(compile(src, f"<tool {name}>", "exec"), namespace)  # noqa: S102 - 只拼 schema 里已定义的参数名
    return namespace["_tool"]


def serve(policy: Policy, service: Service, default_path: str | None):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("efw-studio")

    async def dispatch(name: str, arguments: dict[str, Any]) -> str:
        args = {k: v for k, v in dict(arguments or {}).items() if v is not None}
        if not args.get("path") and default_path and name not in {
                "efw_set", "efw_fire", "efw_force", "efw_release", "efw_stop", "efw_command"}:
            args["path"] = default_path
        is_write = any(n == name for n, _d, _g, _s in WRITE_TOOLS)
        try:
            if is_write:
                policy.check(name, args)
            result = await asyncio.to_thread(run_tool, policy, service, name, args)
            if is_write:
                policy.record(name, args, True)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except ServiceError as exc:
            if is_write:
                policy.record(name, args, False, str(exc))
            return json.dumps({"error": {"code": exc.code, "message": str(exc)}}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - 一次工具失败不能拖垮整个 server
            return json.dumps({"error": {"code": "INTERNAL", "message": str(exc)}}, ensure_ascii=False)

    scoped_out = {"efw_set", "efw_fire", "efw_force", "efw_release", "efw_stop", "efw_command"}
    for name, description, _group, schema in READ_TOOLS + (WRITE_TOOLS if policy.allow_write else []):
        schema = dict(schema)
        if default_path and name not in scoped_out:
            # 命令行给了默认项目时，工具不必再要求 path
            schema["required"] = [k for k in schema.get("required", []) if k != "path"]
        handler = _make_handler(name, schema)
        handler.__globals__["dispatch"] = dispatch
        server.tool(name=name, description=description)(handler)
    return server


def agent_state(self_service: Service, path: str, session: str | None) -> dict[str, Any]:
    """一次性状态读取：正在跑的会话优先，否则取最近一次录制的末帧。"""
    from .debug import list_runs
    live = self_service.sessions
    if session and session in live:
        obj = live[session]["obj"]
        with obj.lock:
            frames = list(obj.buf)
        return {"source": "live", "session": session, "state": obj.state, "t": obj.t,
                "speed": obj.speed, "frames": frames[-20:]}
    if session:
        raise ServiceError("INVALID", f"本进程没有会话 {session}")
    runs = list_runs(Path(path))
    if not runs:
        return {"source": "none", "note": "没有正在运行的会话，也没有录制；先 efw_start（需 --allow-write）"}
    newest = runs[0]["name"]
    frames: list[dict] = []
    threading_event("agent", Path(path), newest, 400, frames)
    snaps = [f for f in frames if f.get("e") == "snap"]
    return {"source": "recording", "run": newest, "frames": len(frames),
            "t": snaps[-1].get("t") if snaps else None,
            "signals": snaps[-1].get("s", {}) if snaps else {},
            "outputs": snaps[-1].get("o", {}) if snaps else {},
            "queues": snaps[-1].get("q", {}) if snaps else {},
            "machines": snaps[-1].get("m", {}) if snaps else {}}


Service.agent_state = agent_state  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="efw-mcp", description="EFW 的 MCP server（默认只读）")
    parser.add_argument("path", nargs="?", help="默认项目目录，工具调用里可省略 path")
    parser.add_argument("--allow-write", action="store_true", help="允许写操作（启动会话、改参数、触发事件、生成代码）")
    parser.add_argument("--allow-targets", default="virtual",
                        help="允许写入的目标，逗号分隔，例如 virtual,serial,tcp")
    args = parser.parse_args(argv)
    targets = [t.strip() for t in args.allow_targets.split(",") if t.strip()]
    root = Path(args.path) if args.path else None
    policy = Policy(args.allow_write, targets, root)
    service = Service(lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
    print(f"[efw-mcp] 只读模式" if not args.allow_write else
          f"[efw-mcp] 可写模式，允许目标 {targets}；写入会记到 .efw/agent-audit.jsonl", file=sys.stderr)
    try:
        serve(policy, service, args.path).run(transport="stdio")
    except KeyboardInterrupt:
        pass
    finally:
        service.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())