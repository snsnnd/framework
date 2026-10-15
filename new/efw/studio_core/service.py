"""所有应用命令；界面（Electron）与命令行共用这一个调度表。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable

from . import codegen, project
from .debug import ProcTransport, Recorder, ReplaySession, Session, SerialTransport, TcpTransport, build_virtual, list_runs, runtime_dir
from .fsutil import ServiceError, safe_path
from .model import model_hash

VERSION = "0.2.0"

TEMPLATES = [
    {"id": "thermostat", "label": "恒温控制", "text": "PID 闭环 + 过热保护状态机，含自带的加热仿真，打开就能看到曲线。",
     "features": ["PID", "状态机", "事件", "仿真闭环"]},
    {"id": "traffic", "label": "信号灯", "text": "纯状态机：超时切换、按钮事件抢占，无需写任何 C 就能运行。", "features": ["状态机", "超时", "事件"]},
    {"id": "sampler", "label": "采样与批处理", "text": "高速采样通过队列交给慢速处理，观察队列深度与丢包。", "features": ["队列", "自定义 C", "滤波"]},
    {"id": "blank", "label": "空白项目", "text": "从零开始。", "features": []},
]


class Service:
    def __init__(self, notify: Callable[[dict], None] | None = None):
        self.notify = notify or (lambda event: None)
        self.sessions: dict[str, dict] = {}

    def dispatch(self, method: str, params: dict | None = None):
        params = params or {}
        table = {
            "system.info": self.info, "templates.list": lambda: TEMPLATES,
            "project.create": project.create_project, "project.open": project.open_project,
            "project.save": project.save_project, "project.analyze": project.analyze,
            "project.stub": project.stubs,
            "file.read": project.read_file, "file.write": project.write_file, "file.create": project.create_file,
            "generate.preview": project.preview, "generate.commit": project.commit,
            "debug.start": self.debug_start, "debug.control": self.debug_control,
            "debug.send": self.debug_send, "debug.stop": self.debug_stop, "debug.runs": self.debug_runs,
        }
        if method not in table:
            raise ServiceError("INVALID", f"未知方法：{method}")
        try:
            return table[method](**params)
        except TypeError as exc:
            raise ServiceError("INVALID", f"参数不正确：{exc}") from exc

    def info(self):
        return {"version": VERSION, "protocol": 2, "runtime": str(runtime_dir())}

    # ---- 调试 ----
    def _emit(self, event: dict) -> None:
        self.notify(event)

    def debug_start(self, path: str, target: dict, model: dict | None = None) -> dict:
        self.stop_all()
        root = project.project_root(path)
        if model is None:
            model = project.open_project(path)["model"]
        info = project.analyze(path, model)
        if not info["ok"]:
            first = next(d for d in info["diagnostics"] if d["level"] == "error")
            raise ServiceError("VALIDATION", f"模型有错误，无法调试：{first['message']}")
        manifest = json.loads(codegen.gen_manifest(model))
        kind = (target or {}).get("kind")
        sid = uuid.uuid4().hex[:8]
        tick = int(model.get("tick_ms", 1))
        h = model_hash(model)
        if kind == "replay":
            name = str(target.get("run", ""))
            if "/" in name or "\\" in name or not name.endswith(".jsonl"):
                raise ServiceError("INVALID", "无效的记录文件名")
            session = ReplaySession(sid, safe_path(root, f".efw/runs/{name}"), self._emit, h)
        else:
            if kind == "virtual":
                transport, pacer = ProcTransport(build_virtual(root, model), root), True
            elif kind == "serial":
                transport, pacer = SerialTransport(str(target["port"]), int(target.get("baud", 115200))), False
            elif kind == "tcp":
                transport, pacer = TcpTransport(str(target["host"]), int(target["port"])), False
            else:
                raise ServiceError("INVALID", f"未知调试目标：{kind}")
            session = Session(sid, kind, transport, self._emit, Recorder(root, kind, h, model["name"]), h, tick, pacer)
        self.sessions[sid] = {"obj": session, "args": (path, target, model)}
        session.start()
        return {"session": sid, "kind": kind, "manifest": manifest, "state": session.state}

    def _get(self, sid: str):
        if sid not in self.sessions:
            raise ServiceError("NOT_FOUND", "调试会话不存在或已结束")
        return self.sessions[sid]

    def debug_control(self, session: str, action: str, value=None) -> dict:
        entry = self._get(session)
        if action == "reset":
            path, target, model = entry["args"]
            return self.debug_start(path, target, model)
        entry["obj"].control(action, value)
        return {"session": session}

    def debug_send(self, session: str, line: str) -> dict:
        self._get(session)["obj"].send(line)
        return {"session": session}

    def debug_stop(self, session: str) -> dict:
        entry = self.sessions.pop(session, None)
        if entry:
            entry["obj"].stop()
        return {}

    def debug_runs(self, path: str) -> list:
        return list_runs(project.project_root(path))

    def stop_all(self) -> None:
        for sid in list(self.sessions):
            self.debug_stop(sid)
