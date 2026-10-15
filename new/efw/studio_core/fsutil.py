"""文件系统边界：安全路径、原子写入、修订号。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


class ServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ServiceError("INVALID", f"非法的项目内路径：{name}")
    if name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ServiceError("INVALID", f"路径必须位于项目内：{name}")
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ServiceError("INVALID", f"不接受符号链接：{name}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ServiceError("INVALID", f"路径越界：{name}")
    return current


def source_path(root: Path, name: str) -> Path:
    path = safe_path(root, name)
    if PurePosixPath(name).parts[0] not in {"src", "board"} or path.suffix not in {".c", ".h", ".inc"}:
        raise ServiceError("INVALID", "用户源码必须位于 src/ 或 board/，且是 .c / .h / .inc 文件")
    return path


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".efw-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ServiceError("NOT_FOUND", f"文件不存在：{path}") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ServiceError("INVALID", f"JSON 无法解析：{path.name}：{exc}") from exc
