"""JSON Lines 服务：stdout 只输出协议；请求响应带 id，通知不带 id。"""
from __future__ import annotations

import json
import sys
import threading
import traceback

from .fsutil import ServiceError
from .service import Service

_lock = threading.Lock()


def emit(obj: dict) -> None:
    text = json.dumps(obj, ensure_ascii=False, allow_nan=False)
    with _lock:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    service = Service(emit)
    try:
        for line in sys.stdin:
            request: object = {}
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or not isinstance(request.get("method"), str) or not isinstance(request.get("params", {}), dict):
                    raise ServiceError("INVALID", "请求必须包含 method 和对象 params")
                emit({"id": request.get("id"), "result": service.dispatch(request["method"], request.get("params"))})
            except Exception as exc:  # noqa: BLE001 - 服务不能因单个请求崩溃
                code = exc.code if isinstance(exc, ServiceError) else "INVALID" if isinstance(exc, (ValueError, TypeError, KeyError)) else "INTERNAL"
                if code == "INTERNAL":
                    traceback.print_exc(file=sys.stderr)
                emit({"id": request.get("id") if isinstance(request, dict) else None, "error": {"code": code, "message": str(exc)}})
    finally:
        service.stop_all()


if __name__ == "__main__":
    main()
