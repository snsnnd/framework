#!/usr/bin/env python3
"""Agent-facing LiteTune CLI.
The CLI is intentionally thin: it starts/stops daemon.py, validates runtime
state, sends one NDJSON request over a Unix Domain Socket, and prints JSON.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from typing import Any

EXIT_OK = 0
EXIT_ARGS = 1
EXIT_DAEMON = 2
EXIT_BUSINESS = 3
EXIT_TIMEOUT = 4
EXIT_PROTOCOL = 5
EXIT_IO = 6
DEFAULT_TIMEOUT = 5.0
MAX_LINE_BYTES = 1024 * 1024


class LtError(Exception):
    exit_code = EXIT_IO
    code = "IO_ERROR"

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ArgsError(LtError):
    exit_code = EXIT_ARGS
    code = "INVALID_ARGS"


class DaemonConnectError(LtError):
    exit_code = EXIT_DAEMON
    code = "DAEMON_NOT_RUNNING"


class DaemonConfigMismatchError(LtError):
    exit_code = EXIT_DAEMON
    code = "DAEMON_CONFIG_MISMATCH"


class BusinessError(LtError):
    exit_code = EXIT_BUSINESS
    code = "MCU_ERROR"


class TimeoutError(LtError):
    exit_code = EXIT_TIMEOUT
    code = "TIMEOUT"


class ProtocolError(LtError):
    exit_code = EXIT_PROTOCOL
    code = "PROTOCOL_ERROR"


class LocalIOError(LtError):
    exit_code = EXIT_IO
    code = "LOCAL_IO_ERROR"


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgsError(message)


# ---------------------------------------------------------------------------
# Paths, JSON and daemon metadata


def code_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def default_runtime_dir() -> str:
    return os.path.abspath(os.path.join(code_dir(), "..", "runtime"))


def daemon_py_path() -> str:
    return os.path.join(code_dir(), "daemon.py")


def daemon_json_path(runtime: str) -> str:
    return os.path.join(runtime, "daemon.json")


def default_socket_path(runtime: str) -> str:
    return os.path.join(runtime, "litetune.sock")


def emit(data: dict[str, Any], pretty: bool = False) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LocalIOError("cannot read daemon.json", {"path": path, "errno": exc.errno, "error": str(exc)})
    except json.JSONDecodeError as exc:
        raise ProtocolError("daemon.json is invalid JSON", {"path": path, "line": exc.lineno, "column": exc.colno})
    if not isinstance(data, dict):
        raise ProtocolError("daemon.json must be a JSON object", {"path": path})
    return data


def daemon_meta(runtime: str) -> dict[str, Any]:
    return read_json(daemon_json_path(runtime)) or {}


def socket_path(runtime: str) -> str:
    meta = daemon_meta(runtime)
    value = meta.get("socket_path") or meta.get("socket") or meta.get("uds_path") or meta.get("uds")
    if isinstance(value, str) and value:
        return value if os.path.isabs(value) else os.path.abspath(os.path.join(runtime, value))
    return default_socket_path(runtime)


def pid_from_meta(meta: dict[str, Any]) -> int | None:
    value = meta.get("pid")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pid_alive(pid: int | None) -> bool | None:
    if pid is None:
        return None
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def requested_port(args: argparse.Namespace) -> str | None:
    port = getattr(args, "port", None)
    if port:
        return str(port)
    return None


def requested_baud(args: argparse.Namespace) -> int | None:
    if not hasattr(args, "baud"):
        return None
    try:
        return int(args.baud)
    except (TypeError, ValueError):
        return None


def status_port(status: dict[str, Any]) -> str | None:
    value = status.get("port")
    if value is None and isinstance(status.get("daemon"), dict):
        value = status["daemon"].get("port")
    return str(value) if value is not None else None


def status_baud(status: dict[str, Any]) -> int | None:
    value = status.get("baud")
    if value is None and isinstance(status.get("daemon"), dict):
        value = status["daemon"].get("baud")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def port_baud_mismatches(args: argparse.Namespace, status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mismatches: dict[str, dict[str, Any]] = {}
    req_port = requested_port(args)
    actual_port = status_port(status)
    if req_port is not None and actual_port is not None and req_port != actual_port:
        mismatches["port"] = {"requested": req_port, "actual": actual_port}
    req_baud = requested_baud(args)
    actual_baud = status_baud(status)
    if req_baud is not None and actual_baud is not None and req_baud != actual_baud:
        mismatches["baud"] = {"requested": req_baud, "actual": actual_baud}
    return mismatches


def ensure_status_matches_requested(args: argparse.Namespace, status_payload: dict[str, Any]) -> None:
    status = status_payload.get("daemon") if isinstance(status_payload.get("daemon"), dict) else {}
    meta = status_payload.get("metadata") if isinstance(status_payload.get("metadata"), dict) else {}
    status_mismatches = port_baud_mismatches(args, status)
    meta_mismatches = port_baud_mismatches(args, meta)
    if status_mismatches or meta_mismatches:
        raise DaemonConfigMismatchError(
            "connectable daemon does not match requested --port/--baud",
            {
                "requested": {"port": requested_port(args), "baud": requested_baud(args)},
                "daemon": {"port": status_port(status), "baud": status_baud(status)},
                "metadata": {"port": status_port(meta), "baud": status_baud(meta)},
                "mismatches": {"daemon": status_mismatches, "metadata": meta_mismatches},
            },
        )


# ---------------------------------------------------------------------------
# UDS NDJSON client


def json_line(data: dict[str, Any]) -> bytes:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(raw) > MAX_LINE_BYTES:
        raise ProtocolError("request exceeds UDS line limit")
    return raw


def connect(path: str, timeout: float) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
    except socket.timeout as exc:
        sock.close()
        raise TimeoutError("timed out connecting to daemon", {"socket_path": path}) from exc
    except OSError as exc:
        sock.close()
        if exc.errno in (errno.ENOENT, errno.ECONNREFUSED, errno.ENOTSOCK, errno.EACCES):
            raise DaemonConnectError("daemon is not connectable", {"socket_path": path, "errno": exc.errno, "error": str(exc)})
        raise LocalIOError("socket connect failed", {"socket_path": path, "errno": exc.errno, "error": str(exc)}) from exc
    return sock


def read_response_line(file_obj: Any) -> bytes:
    line = file_obj.readline(MAX_LINE_BYTES + 1)
    if len(line) > MAX_LINE_BYTES:
        raise ProtocolError("daemon response line too large")
    if not line:
        raise ProtocolError("daemon closed without a response")
    if not line.endswith(b"\n"):
        raise ProtocolError("daemon response is not newline terminated")
    return line


def decode_response(line: bytes) -> dict[str, Any]:
    try:
        data = json.loads(line.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ProtocolError("daemon response is not UTF-8", str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError("daemon response is not JSON", {"line": exc.lineno, "column": exc.colno}) from exc
    if not isinstance(data, dict):
        raise ProtocolError("daemon response must be a JSON object")
    return data


def daemon_request(runtime: str, op: str, params: dict[str, Any] | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    request = {"id": str(uuid.uuid4()), "op": op, "params": params or {}}
    sock = connect(socket_path(runtime), timeout)
    try:
        with sock.makefile("rwb", buffering=0) as file_obj:
            file_obj.write(json_line(request))
            response = decode_response(read_response_line(file_obj))
    except socket.timeout as exc:
        raise TimeoutError("timed out waiting for daemon response", {"op": op}) from exc
    except OSError as exc:
        raise LocalIOError("socket I/O failed", {"errno": exc.errno, "error": str(exc), "op": op}) from exc
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if response.get("ok") is False:
        err = response.get("error") if isinstance(response.get("error"), dict) else {"message": "daemon error"}
        code = err.get("code")
        if code == "TIMEOUT":
            raise TimeoutError(err.get("message", "daemon reported timeout"), err)
        if code in {"BAD_REQUEST", "INVALID_ARGS"}:
            raise ArgsError(err.get("message", "daemon rejected request arguments"), err)
        raise BusinessError(err.get("message", "daemon reported an error"), err)
    result = response.get("result", {})
    if not isinstance(result, dict):
        raise ProtocolError("daemon result must be a JSON object", response)
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Commands


def daemon_status_payload(args: argparse.Namespace, require_connect: bool) -> dict[str, Any]:
    meta = daemon_meta(args.runtime)
    pid = pid_from_meta(meta)
    path = socket_path(args.runtime)
    result: dict[str, Any] = {
        "ok": True,
        "runtime": args.runtime,
        "daemon_json_path": daemon_json_path(args.runtime),
        "daemon_json_exists": bool(meta),
        "socket_path": path,
        "socket_exists": os.path.exists(path),
        "pid": pid,
        "pid_alive": None,
        "connectable": False,
        "metadata": meta,
    }
    try:
        status = daemon_request(args.runtime, "daemon.status", timeout=args.timeout)
    except LtError as exc:
        ensure_status_matches_requested(args, result)
        result["pid_alive"] = pid_alive(pid)
        if require_connect:
            raise
        result["ok"] = False
        result["error"] = error_body(exc)
        return result
    result["pid_alive"] = pid_alive(pid)
    result["connectable"] = True
    result["daemon"] = status
    meta_id = meta.get("daemon_id")
    daemon_id = status.get("daemon_id") or status.get("daemon", {}).get("daemon_id")
    result["daemon_id_matches"] = not meta_id or meta_id == daemon_id
    if not result["daemon_id_matches"]:
        result["ok"] = False
        result["error"] = {"code": "DAEMON_ID_MISMATCH", "message": "socket daemon_id differs from daemon.json"}
    ensure_status_matches_requested(args, result)
    return result


def cmd_daemon_status(args: argparse.Namespace) -> dict[str, Any]:
    return daemon_status_payload(args, require_connect=False)


def daemon_port(args: argparse.Namespace) -> str:
    if getattr(args, "port", None):
        return args.port
    meta_port = daemon_meta(args.runtime).get("port")
    if isinstance(meta_port, str) and meta_port:
        return meta_port
    env_port = os.environ.get("LITETUNE_PORT")
    if env_port:
        return env_port
    raise ArgsError("daemon start requires --port, daemon.json port, or LITETUNE_PORT")


def cmd_daemon_start(args: argparse.Namespace) -> dict[str, Any]:
    os.makedirs(args.runtime, exist_ok=True)
    existing = daemon_status_payload(args, require_connect=False)
    if existing.get("connectable") and existing.get("ok"):
        return {"ok": True, "started": False, "reason": "already_running", "status": existing}
    daemon_py = daemon_py_path()
    if not os.path.exists(daemon_py):
        raise LocalIOError("daemon.py not found", {"path": daemon_py})
    stdout_path = args.daemon_stdout or os.path.join(args.runtime, "daemon.stdout.log")
    cmd = [
        sys.executable,
        daemon_py,
        "--runtime",
        args.runtime,
        "--port",
        daemon_port(args),
        "--baud",
        str(args.baud),
        "--log-max-bytes",
        str(args.log_max_bytes),
        "--telemetry-log",
        args.telemetry_log,
    ]
    if args.host_max_decoded_frame:
        cmd.extend(["--host-max-decoded-frame", str(args.host_max_decoded_frame)])
    if getattr(args, "daemon_arg", None):
        cmd.extend(args.daemon_arg)
    try:
        stdin = open(os.devnull, "rb")
        stdout = open(stdout_path, "ab", buffering=0)
    except OSError as exc:
        raise LocalIOError("cannot open daemon stdio file", {"errno": exc.errno, "error": str(exc), "path": stdout_path}) from exc
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=code_dir(),
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            close_fds=os.name != "nt",
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise LocalIOError("failed to launch daemon", {"errno": exc.errno, "error": str(exc), "cmd": cmd}) from exc
    finally:
        stdin.close()
        stdout.close()
    deadline = time.monotonic() + args.wait
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise LocalIOError("daemon exited during startup", {"returncode": proc.returncode, "stdout": stdout_path})
        last = daemon_status_payload(args, require_connect=False)
        if last.get("connectable"):
            return {"ok": True, "started": True, "pid": proc.pid, "stdout": stdout_path, "status": last}
        time.sleep(0.1)
    raise TimeoutError("daemon did not become connectable", {"pid": proc.pid, "stdout": stdout_path, "last_status": last})


def cmd_daemon_stop(args: argparse.Namespace) -> dict[str, Any]:
    daemon_status_payload(args, require_connect=False)
    try:
        result = daemon_request(args.runtime, "daemon.stop", timeout=args.timeout)
        return {"ok": True, "stopped": True, "via": "uds", "daemon": result}
    except DaemonConnectError as exc:
        if not getattr(args, "force", False):
            raise
        meta = daemon_meta(args.runtime)
        pid = pid_from_meta(meta)
        if pid_alive(pid) is not True:
            return {"ok": True, "stopped": False, "via": "metadata", "reason": "not_running", "connect_error": error_body(exc)}
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as kill_exc:
            raise LocalIOError("failed to terminate daemon pid", {"pid": pid, "errno": kill_exc.errno, "error": str(kill_exc)}) from kill_exc
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            if pid_alive(pid) is not True:
                return {"ok": True, "stopped": True, "via": "signal", "pid": pid}
            time.sleep(0.1)
        raise TimeoutError("daemon pid did not stop", {"pid": pid})


def cmd_daemon_restart(args: argparse.Namespace) -> dict[str, Any]:
    try:
        stopped = cmd_daemon_stop(args)
    except DaemonConnectError:
        if not args.force:
            raise
        stopped = {"ok": True, "stopped": False, "reason": "not_running"}
    time.sleep(0.2)
    started = cmd_daemon_start(args)
    return {"ok": True, "stop": stopped, "start": started}


def cmd_port_list(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return {"ok": True, "ports": [], "warning": "pyserial is not installed"}
    ports = [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in list_ports.comports()]
    return {"ok": True, "ports": ports}


def cmd_schema(args: argparse.Namespace) -> dict[str, Any]:
    return daemon_request(args.runtime, "schema.refresh" if args.refresh else "schema.get", timeout=args.timeout)


def cmd_param_list(args: argparse.Namespace) -> dict[str, Any]:
    return daemon_request(args.runtime, "param.list", timeout=args.timeout)


def cmd_param_get(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"all": args.all}
    if args.names:
        params["names"] = args.names
    if not args.all and not args.names:
        raise ArgsError("param get requires one or more names, or --all")
    return daemon_request(args.runtime, "param.get", params, timeout=args.timeout)


def parse_assignments(assignments: str) -> dict[str, Any]:
    values = {}
    for item in assignments.split(","):
        item = item.strip()
        if not item:
            raise ArgsError("param set contains an empty NAME=VALUE item")
        if "=" not in item:
            raise ArgsError("param set expects NAME=VALUE items")
        name, value = item.split("=", 1)
        name = name.strip()
        if not name:
            raise ArgsError("param set contains an empty parameter name")
        values[name] = parse_scalar(value.strip())
    return values


def parse_scalar(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def cmd_param_set(args: argparse.Namespace) -> dict[str, Any]:
    values = parse_assignments(args.assignments)
    timeout = getattr(args, "command_timeout", None)
    params: dict[str, Any] = {"values": values}
    if timeout is not None:
        params["timeout_s"] = timeout
    return daemon_request(args.runtime, "param.set", params, timeout=args.timeout)


def cmd_run(args: argparse.Namespace) -> dict[str, Any]:
    params = {"name": args.name}
    if args.command_timeout:
        params["timeout_s"] = args.command_timeout
    return daemon_request(args.runtime, "cmd.run", params, timeout=args.timeout)


def cmd_log(args: argparse.Namespace) -> dict[str, Any]:
    params = {"num": args.num, "type": args.type}
    if args.follow:
        return follow_log(args)
    return daemon_request(args.runtime, "log.tail", params, timeout=args.timeout)


def follow_log(args: argparse.Namespace) -> dict[str, Any]:
    status = daemon_status_payload(args, require_connect=True)
    log_path = status.get("daemon", {}).get("log_path") or status.get("metadata", {}).get("log_path")
    if not log_path:
        raise LocalIOError("daemon status did not report log_path")
    emit(daemon_request(args.runtime, "log.tail", {"num": args.num, "type": args.type}, timeout=args.timeout), args.pretty)
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip("\n"), flush=True)
                else:
                    time.sleep(0.2)
    except KeyboardInterrupt:
        return {"ok": True, "follow_interrupted": True, "log_path": log_path}
    except OSError as exc:
        raise LocalIOError("cannot follow log", {"path": log_path, "errno": exc.errno, "error": str(exc)}) from exc


# ---------------------------------------------------------------------------
# Parser and process exit


def add_common(parser: argparse.ArgumentParser, defaults: bool = False) -> None:
    parser.add_argument("--runtime", default=default_runtime_dir() if defaults else argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT if defaults else argparse.SUPPRESS)
    parser.add_argument("--pretty", action="store_true", default=False if defaults else argparse.SUPPRESS)


def add_daemon_serial_options(parser: argparse.ArgumentParser, include_defaults: bool = False) -> None:
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=115200 if include_defaults else argparse.SUPPRESS)


def add_daemon_start_options(parser: argparse.ArgumentParser) -> None:
    add_daemon_serial_options(parser, include_defaults=True)
    parser.add_argument("--wait", type=float, default=5.0)
    parser.add_argument("--daemon-stdout")
    parser.add_argument("--daemon-log", dest="daemon_stdout")
    parser.add_argument("--daemon-arg", action="append")
    parser.add_argument("--log-max-bytes", type=int, default=0)
    parser.add_argument("--telemetry-log", default="all")
    parser.add_argument("--host-max-decoded-frame", type=int, default=2048)


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="lt.py", description="LiteTune Agent-facing CLI")
    add_common(parser, defaults=True)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("port-list"); add_common(p); p.set_defaults(handler=cmd_port_list)
    daemon = sub.add_parser("daemon"); add_common(daemon)
    dsub = daemon.add_subparsers(dest="daemon_command", required=True)
    p = dsub.add_parser("start"); add_common(p); add_daemon_start_options(p); p.set_defaults(handler=cmd_daemon_start)
    p = dsub.add_parser("status"); add_common(p); add_daemon_serial_options(p); p.set_defaults(handler=cmd_daemon_status)
    p = dsub.add_parser("stop"); add_common(p); add_daemon_serial_options(p); p.add_argument("--force", action="store_true"); p.add_argument("--wait", type=float, default=5.0); p.set_defaults(handler=cmd_daemon_stop)
    p = dsub.add_parser("restart"); add_common(p); p.add_argument("--force", action="store_true"); add_daemon_start_options(p); p.set_defaults(handler=cmd_daemon_restart)
    p = sub.add_parser("schema"); add_common(p); p.add_argument("--refresh", action="store_true"); p.set_defaults(handler=cmd_schema)
    param = sub.add_parser("param"); add_common(param)
    psub = param.add_subparsers(dest="param_command", required=True)
    p = psub.add_parser("list"); add_common(p); p.set_defaults(handler=cmd_param_list)
    p = psub.add_parser("get"); add_common(p); p.add_argument("names", nargs="*"); p.add_argument("--all", action="store_true"); p.set_defaults(handler=cmd_param_get)
    p = psub.add_parser("set"); add_common(p); p.add_argument("assignments", metavar="NAME=VALUE[,NAME=VALUE...]"); p.add_argument("--command-timeout", type=float); p.set_defaults(handler=cmd_param_set)
    p = sub.add_parser("cmd"); add_common(p); p.add_argument("name"); p.add_argument("--command-timeout", type=float); p.set_defaults(handler=cmd_run)
    p = sub.add_parser("log"); add_common(p); p.add_argument("--num", "--lines", "--tail", "-n", dest="num", type=int, default=10); p.add_argument("--type", "--filter", dest="type"); p.add_argument("--follow", "-f", action="store_true"); p.set_defaults(handler=cmd_log)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    args.runtime = os.path.abspath(args.runtime)
    if args.timeout <= 0:
        raise ArgsError("--timeout must be positive")
    if hasattr(args, "wait") and args.wait <= 0:
        raise ArgsError("--wait must be positive")
    if hasattr(args, "num") and args.num < 0:
        raise ArgsError("--num must be non-negative")


def error_body(exc: LtError) -> dict[str, Any]:
    code = exc.code
    if isinstance(exc.details, dict) and isinstance(exc.details.get("code"), str):
        code = exc.details["code"]
    body = {"code": code, "message": exc.message, "exit_code": exc.exit_code}
    if exc.details is not None:
        body["details"] = exc.details
    return body


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        validate_args(args)
        result = args.handler(args)
        emit(result, args.pretty)
        return EXIT_OK
    except LtError as exc:
        emit({"ok": False, "error": error_body(exc)})
        return exc.exit_code
if __name__ == "__main__":
    sys.exit(main())
