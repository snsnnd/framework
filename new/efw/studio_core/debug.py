"""调试会话：虚拟目标 / 串口 / TCP / 回放，共用一套帧协议。"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from . import codegen
from .fsutil import ServiceError, atomic_write, digest, safe_path
from .model import model_hash

ALLOWED = {"hello", "dump", "rate", "set", "force", "release", "fire", "push", "pause", "resume", "state"}
SAFE_LINE = re.compile(r"^[A-Za-z0-9_.\- +]{1,80}$")
MAX_FRAMES_PER_PUSH = 400


def runtime_dir() -> Path:
    if os.environ.get("EFW_RUNTIME"):
        return Path(os.environ["EFW_RUNTIME"])
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "runtime"


def find_cc() -> str:
    for candidate in ([os.environ["EFW_CC"]] if os.environ.get("EFW_CC") else []) + ["cc", "gcc", "clang"]:
        found = shutil.which(candidate)
        if found:
            return found
    raise ServiceError("NO_COMPILER", "找不到 C 编译器。安装 gcc / clang（Windows 可用 MSYS2 或 LLVM），或设置环境变量 EFW_CC。")


def build_virtual(root: Path, model: dict) -> Path:
    """生成并编译虚拟目标；按 模型哈希 + 用户源码内容 缓存。"""
    src_files = sorted(p for p in (root / "src").rglob("*") if p.is_file() and not p.is_symlink() and p.suffix in {".c", ".h", ".inc"}) if (root / "src").is_dir() else []
    key = digest(model_hash(model) + "".join(digest(p.read_bytes()) for p in src_files))[:16]
    build = safe_path(root, f".efw/build/{key}")
    exe = build / ("virtual.exe" if os.name == "nt" else "virtual")
    if exe.exists():
        return exe
    for name, content in codegen.generate(model).items():
        if name != "manifest.json":
            atomic_write(build / name, content)
    rt = runtime_dir()
    cmd = [find_cc(), "-std=c99", "-O1", "-DAPP_VIRTUAL", f"-I{build}", f"-I{rt / 'include'}", f"-I{root / 'src'}",
           *[str(p) for p in src_files if p.suffix == ".c"], str(build / "app_core.c"), str(build / "app_virtual.c"),
           *[str(rt / "src" / "core" / n) for n in ("scheduler.c", "diagnostic.c", "msgq.c")], "-lm", "-o", str(exe)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ServiceError("BUILD", "编译超时（120 秒）") from exc
    if done.returncode != 0:
        raise ServiceError("BUILD", "虚拟目标编译失败：\n" + (done.stderr or done.stdout)[-3500:])
    olds = sorted((root / ".efw" / "build").iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[6:]
    for old in olds:
        shutil.rmtree(old, ignore_errors=True)
    return exe


# ---------------- 传输层 ----------------

class ProcTransport:
    def __init__(self, exe: Path, cwd: Path):
        self.p = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", bufsize=1, cwd=cwd)

    def lines(self) -> Iterator[str]:
        assert self.p.stdout
        yield from self.p.stdout

    def write(self, line: str) -> None:
        assert self.p.stdin
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def close(self) -> None:
        try:
            self.write("quit")
        except (OSError, ValueError):
            pass
        try:
            self.p.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.p.kill()


class SerialTransport:
    def __init__(self, port: str, baud: int):
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise ServiceError("MISSING", "串口调试需要 pyserial（uv add pyserial）") from exc
        try:
            self.s = serial.Serial(port, baud, timeout=0.2)
        except Exception as exc:  # noqa: BLE001 - pyserial 的异常类型很多
            raise ServiceError("CONNECT", f"无法打开串口 {port}：{exc}") from exc
        self.closed = False

    def lines(self) -> Iterator[str]:
        buf = b""
        while not self.closed:
            try:
                chunk = self.s.read(256)
            except Exception:  # noqa: BLE001
                return
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                yield raw.decode("utf-8", errors="replace")

    def write(self, line: str) -> None:
        self.s.write((line + "\n").encode("utf-8"))

    def close(self) -> None:
        self.closed = True
        try:
            self.s.close()
        except Exception:  # noqa: BLE001
            pass


class TcpTransport:
    def __init__(self, host: str, port: int):
        try:
            self.sock = socket.create_connection((host, int(port)), timeout=5)
        except OSError as exc:
            raise ServiceError("CONNECT", f"无法连接 {host}:{port}：{exc}") from exc
        self.sock.settimeout(None)
        self.f = self.sock.makefile("r", encoding="utf-8", errors="replace", newline="\n")

    def lines(self) -> Iterator[str]:
        try:
            yield from self.f
        except (OSError, ValueError):
            return

    def write(self, line: str) -> None:
        self.sock.sendall((line + "\n").encode("utf-8"))

    def close(self) -> None:
        for closer in (self.f.close, lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
            try:
                closer()
            except (OSError, ValueError):
                pass


class Recorder:
    def __init__(self, root: Path, kind: str, model_hash_: str, name: str):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = safe_path(root, f".efw/runs/{stamp}-{kind}.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "w", encoding="utf-8")
        self.last_flush = time.monotonic()
        self.write({"e": "session", "kind": kind, "hash": model_hash_, "name": name, "started": datetime.now().isoformat(timespec="seconds")})
        runs = sorted(self.path.parent.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[20:]
        for old in runs:
            old.unlink(missing_ok=True)

    def write(self, obj: dict) -> None:
        self.f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
        if time.monotonic() - self.last_flush > 0.5:
            self.f.flush()
            self.last_flush = time.monotonic()

    def close(self) -> None:
        try:
            self.f.close()
        except OSError:
            pass


def thin(frames: list[dict]) -> list[dict]:
    if len(frames) <= MAX_FRAMES_PER_PUSH:
        return frames
    snaps = [f for f in frames if f.get("e") == "snap"]
    keep = {id(f) for f in snaps[-(MAX_FRAMES_PER_PUSH // 2):]}
    return [f for f in frames if f.get("e") != "snap" or id(f) in keep]


def valid_command(line: str) -> str:
    line = line.strip()
    if not SAFE_LINE.match(line) or line.split()[0] not in ALLOWED:
        raise ServiceError("INVALID", f"不允许的调试命令：{line[:40]}")
    return line


class Session:
    """live 会话（串口 / TCP）与虚拟目标共用；pacer=True 时由本会话推进仿真时间。"""

    def __init__(self, sid: str, kind: str, transport, emit: Callable[[dict], None], recorder: Recorder | None,
                 expected_hash: str, tick_ms: int, pacer: bool):
        self.id, self.kind, self.transport, self.emit_fn, self.recorder = sid, kind, transport, emit, recorder
        self.expected_hash, self.tick, self.pacer = expected_hash, max(1, tick_ms), pacer
        self.state = "paused" if pacer else "running"
        self.speed = 1.0
        self.t = 0
        self.buf: list[dict] = []
        self.lock = threading.Lock()
        self.idle = threading.Event()
        self.stop_flag = threading.Event()
        self.write_lock = threading.Lock()

    def status(self, message: str = "") -> None:
        self.emit_fn({"event": "debug.status", "session": self.id, "state": self.state, "t": self.t, "speed": self.speed, "message": message})

    def start(self) -> None:
        for target in (self._reader, self._flusher) + ((self._pacer,) if self.pacer else ()):
            threading.Thread(target=target, daemon=True).start()
        self.status()
        try:
            self.send_raw("dump")
        except OSError:
            pass

    def _reader(self) -> None:
        try:
            for raw in self.transport.lines():
                raw = raw.strip()
                if not raw.startswith("{"):
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._on_frame(obj)
        finally:
            if not self.stop_flag.is_set():
                self.state = "stopped"
                self.status("目标已断开")
                self.idle.set()

    def _on_frame(self, obj: dict) -> None:
        kind = obj.get("e")
        if isinstance(obj.get("t"), int):
            self.t = obj["t"]
        if kind == "idle":
            self.idle.set()
            return
        if self.recorder:
            self.recorder.write(obj)
        if kind == "hello" and obj.get("hash") != self.expected_hash:
            self.emit_fn({"event": "debug.status", "session": self.id, "state": self.state, "t": self.t, "speed": self.speed,
                          "message": f"目标固件的模型哈希 {obj.get('hash')} 与当前项目 {self.expected_hash} 不一致，界面显示可能与目标不符。请重新生成并烧录。", "warning": True})
        with self.lock:
            self.buf.append(obj)

    def _flusher(self) -> None:
        while not self.stop_flag.wait(0.05):
            with self.lock:
                frames, self.buf = self.buf, []
            if frames:
                self.emit_fn({"event": "debug.frames", "session": self.id, "frames": thin(frames)})

    def _run(self, ms: int) -> bool:
        self.idle.clear()
        try:
            self.send_raw(f"run {ms}")
        except OSError:
            return False
        if not self.idle.wait(30):
            self.state = "error"
            self.status("目标 30 秒没有响应")
            return False
        return not self.stop_flag.is_set() and self.state != "stopped"

    def _pacer(self) -> None:
        while not self.stop_flag.is_set():
            if self.state != "running":
                time.sleep(0.02)
                continue
            began = time.monotonic()
            chunk = 2000 if self.speed <= 0 else max(self.tick, int(50 * self.speed) // self.tick * self.tick)
            if not self._run(chunk):
                return
            if self.speed > 0:
                rest = 0.05 - (time.monotonic() - began)
                if rest > 0:
                    time.sleep(rest)
            else:
                time.sleep(0.001)

    def send_raw(self, line: str) -> None:
        with self.write_lock:
            self.transport.write(line)

    def send(self, line: str) -> None:
        try:
            self.send_raw(valid_command(line))
        except OSError as exc:
            raise ServiceError("CONNECT", f"发送失败：{exc}") from exc

    def control(self, action: str, value=None) -> None:
        if action == "speed":
            self.speed = float(value or 0)
            self.status()
        elif not self.pacer:
            raise ServiceError("INVALID", "真机目标不支持该控制，它自己在运行")
        elif action == "play":
            self.state = "running"
            self.status()
        elif action == "pause":
            self.state = "paused"
            self.status()
        elif action == "step":
            if self.state == "running":
                raise ServiceError("INVALID", "请先暂停再单步")
            self._run(max(self.tick, int(value or 100)))
            self.status()
        else:
            raise ServiceError("INVALID", f"未知控制：{action}")

    def stop(self) -> None:
        if self.stop_flag.is_set():
            return
        self.stop_flag.set()
        self.state = "stopped"
        self.transport.close()
        with self.lock:
            frames, self.buf = self.buf, []
        if frames:
            self.emit_fn({"event": "debug.frames", "session": self.id, "frames": thin(frames)})
        if self.recorder:
            self.recorder.close()
        self.status()


class ReplaySession:
    def __init__(self, sid: str, path: Path, emit: Callable[[dict], None], expected_hash: str):
        lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.startswith("{")]
        header = next((x for x in lines if x.get("e") == "session"), {})
        self.frames = [x for x in lines if x.get("e") != "session"]
        self.id, self.emit_fn, self.state, self.speed, self.t = sid, emit, "paused", 1.0, 0
        self.end = max((f.get("t", 0) for f in self.frames), default=0)
        self.warning = "" if header.get("hash") == expected_hash else f"这份记录来自另一个模型版本（{header.get('hash')}），当前项目为 {expected_hash}。"
        self.stop_flag = threading.Event()
        self.index = 0

    def status(self, message: str = "") -> None:
        self.emit_fn({"event": "debug.status", "session": self.id, "state": self.state, "t": self.t, "speed": self.speed, "message": message or self.warning, "end": self.end})

    def start(self) -> None:
        self.status()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self.stop_flag.is_set():
            if self.state != "running":
                time.sleep(0.02)
                continue
            began = time.monotonic()
            self.t += 2000 if self.speed <= 0 else int(50 * self.speed)
            out = []
            while self.index < len(self.frames) and self.frames[self.index].get("t", self.t) <= self.t:
                out.append(self.frames[self.index])
                self.index += 1
            if out:
                self.emit_fn({"event": "debug.frames", "session": self.id, "frames": thin(out)})
            if self.index >= len(self.frames):
                self.state = "ended"
                self.status("回放结束")
                return
            time.sleep(max(0.0, 0.05 - (time.monotonic() - began)) if self.speed > 0 else 0.001)

    def send(self, line: str) -> None:
        raise ServiceError("INVALID", "回放中不能向目标发送命令")

    def control(self, action: str, value=None) -> None:
        if action == "speed":
            self.speed = float(value or 0)
        elif action in ("play", "pause"):
            if self.state != "ended":
                self.state = "running" if action == "play" else "paused"
        else:
            raise ServiceError("INVALID", f"回放不支持：{action}")
        self.status()

    def stop(self) -> None:
        self.stop_flag.set()
        self.state = "stopped"
        self.status()


def list_runs(root: Path) -> list[dict]:
    base = root / ".efw" / "runs"
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            first = json.loads(p.open(encoding="utf-8").readline())
        except (OSError, json.JSONDecodeError):
            first = {}
        out.append({"name": p.name, "size": p.stat().st_size, "kind": first.get("kind", "?"), "hash": first.get("hash", ""), "started": first.get("started", "")})
    return out
