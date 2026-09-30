"""项目：打开 / 保存 / 源码 / 分析 / 生成（预览 → token → 提交）。"""
from __future__ import annotations

import difflib
import json
import os
import uuid
from pathlib import Path

from . import codegen
from .fsutil import ServiceError, atomic_write, digest, json_text, load_json, safe_path, source_path
from .model import analyze as analyze_model, fn_signatures
from .templates import IO_HEADER, LOGIC_HEADER, build, stub
from .source_template import check_edit, fixed_parts
from .model import find_definitions

MAX_SOURCE = 1_000_000
CMAKE_SNIPPET = '''# 在你的 CMake 工程里：
#   set(EFW_RUNTIME_DIR /path/to/efw/runtime)
#   include(generated/efw_app.cmake)
#   add_executable(app ${EFW_APP_SOURCES} main.c)   # main.c 调用 app_init() / app_tick()
#   target_include_directories(app PRIVATE ${EFW_APP_INCLUDES})
file(GLOB EFW_APP_USER_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_LIST_DIR}/../src/*.c ${CMAKE_CURRENT_LIST_DIR}/../board/*.c)
set(EFW_APP_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/app_core.c
    ${EFW_RUNTIME_DIR}/src/core/scheduler.c
    ${EFW_RUNTIME_DIR}/src/core/diagnostic.c
    ${EFW_RUNTIME_DIR}/src/core/msgq.c
    ${EFW_APP_USER_SOURCES})
set(EFW_APP_INCLUDES ${CMAKE_CURRENT_LIST_DIR} ${EFW_RUNTIME_DIR}/include)
'''


def project_root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if root.is_file() and root.name == "efw.json":
        root = root.parent
    return root


def list_sources(root: Path) -> list[str]:
    names = []
    for folder in ("src", "board"):
        base = root / folder
        if not base.is_dir() or base.is_symlink():
            continue
        for item in sorted(base.rglob("*")):
            if item.is_symlink() or not item.is_file() or item.suffix not in {".c", ".h", ".inc"}:
                continue
            names.append(item.relative_to(root).as_posix())
    return names


def read_sources(root: Path) -> dict[str, str]:
    out = {}
    for name in list_sources(root):
        path = safe_path(root, name)
        if path.stat().st_size <= MAX_SOURCE:
            out[name] = path.read_text(encoding="utf-8", errors="replace")
    return out


def revision(root: Path) -> str:
    parts = []
    for name in ("efw.json", ".efw/layout.json"):
        p = safe_path(root, name)
        parts.append(digest(p.read_bytes()) if p.exists() else "-")
    return digest("|".join(parts))


def open_project(path: str) -> dict:
    root = project_root(path)
    model = load_json(safe_path(root, "efw.json"))
    layout_file = safe_path(root, ".efw/layout.json")
    layout = load_json(layout_file) if layout_file.exists() else {}
    return {"path": str(root), "model": model, "layout": layout if isinstance(layout, dict) else {},
            "revision": revision(root), "files": list_sources(root)}


def create_project(path: str, name: str, template: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ServiceError("INVALID", "项目名称不能为空")
    root = Path(path).expanduser().resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ServiceError("CONFLICT", "请选择一个不存在或为空的目录来创建项目")
    try:
        model, files, layout = build(template, name.strip())
    except ValueError as exc:
        raise ServiceError("INVALID", str(exc)) from exc
    root.mkdir(parents=True, exist_ok=True)
    atomic_write(root / "efw.json", json_text(model))
    atomic_write(safe_path(root, ".efw/layout.json"), json_text(layout))
    for d in ("src", "board"):
        (root / d).mkdir(exist_ok=True)
    for rel, content in files.items():
        atomic_write(source_path(root, rel), content)
    return open_project(str(root))


def save_project(path: str, model: dict, layout: dict, rev: str) -> dict:
    root = project_root(path)
    if revision(root) != rev:
        raise ServiceError("CONFLICT", "efw.json 已在外部修改。请重新打开项目后再合并你的修改。")
    if not isinstance(model, dict) or not isinstance(layout, dict):
        raise ServiceError("INVALID", "模型与布局必须是对象")
    atomic_write(safe_path(root, "efw.json"), json_text(model))
    atomic_write(safe_path(root, ".efw/layout.json"), json_text(layout))
    return {"revision": revision(root)}


def read_file(path: str, name: str) -> dict:
    root = project_root(path)
    target = source_path(root, name)
    if not target.is_file():
        raise ServiceError("NOT_FOUND", f"文件不存在：{name}")
    if target.stat().st_size > MAX_SOURCE:
        raise ServiceError("INVALID", "文件超过 1 MB，请用外部编辑器")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"name": name, "content": content, "revision": digest(content)}


def write_file(path: str, name: str, content: str, rev: str, add_functions: list[str] | None = None) -> dict:
    current = read_file(path, name)
    if current["revision"] != rev:
        raise ServiceError("CONFLICT", f"{name} 已在外部修改。载入磁盘版本，或另存你的修改后再保存。")
    baseline = current['content']
    if add_functions:
        if not isinstance(add_functions, list) or not all(isinstance(n, str) for n in add_functions) or len(set(add_functions)) != len(add_functions):
            raise ServiceError('INVALID', '函数列表必须是不重复的函数名称。')
        root = project_root(path)
        signatures = {f['name']: f for f in fn_signatures(open_project(path)['model'])}
        definitions = find_definitions(read_sources(root))
        for fn_name in add_functions:
            fn = signatures.get(fn_name)
            if not fn or fn['file'] != name or fn_name in definitions:
                raise ServiceError('CONFLICT', '函数已实现或模型已变化，请重新载入后检查骨架。')
            baseline += '\n' + stub(fn) + '\n'
    check_edit(baseline, content)
    atomic_write(source_path(project_root(path), name), content)
    return read_file(path, name)


def create_file(path: str, name: str, content: str = '#include "app.h"\n') -> dict:
    root = project_root(path)
    target = source_path(root, name)
    if target.exists():
        raise ServiceError("CONFLICT", "文件已存在")
    fixed_parts(content)
    atomic_write(target, content)
    return read_file(path, name)


def analyze(path: str, model: dict, buffers: dict | None = None) -> dict:
    root = project_root(path)
    sources = read_sources(root)
    for name, text in (buffers or {}).items():
        source_path(root, name)
        sources[name] = text
    return analyze_model(model, sources)


def stubs(model: dict, names: list[str]) -> list[dict]:
    """为缺失函数生成骨架，按目标文件分组。"""
    wanted = [f for f in fn_signatures(model) if f["name"] in set(names)]
    grouped: dict[str, list[str]] = {}
    for fn in wanted:
        grouped.setdefault(fn["file"], []).append(stub(fn))
    return [{"file": f, "header": IO_HEADER if f == "board/io.c" else LOGIC_HEADER, "text": "\n".join(texts)} for f, texts in grouped.items()]


# ---------------- 生成 ----------------

def render(model: dict) -> dict[str, str]:
    files = codegen.generate(model)
    files.pop("app_virtual.c")  # 仅虚拟目标使用，由调试会话在 .efw/build 中生成
    files["efw_app.cmake"] = CMAKE_SNIPPET
    return {k: v.rstrip() + "\n" for k, v in files.items()}


def preview(path: str, model: dict) -> dict:
    root = project_root(path)
    info = analyze(path, model)
    if not info["ok"]:
        return {"token": "", "files": [], "blocked": True, "reason": "模型有错误，先修复问题面板里的错误", "analysis": info}
    desired = render(model)
    manifest_file = safe_path(root, ".efw/generated.json")
    owned = load_json(manifest_file) if manifest_file.exists() else {}
    if not isinstance(owned, dict):
        raise ServiceError("INVALID", "生成清单已损坏，请删除 .efw/generated.json 后重试")
    out = safe_path(root, "generated")
    existing: dict[str, str] = {}
    if out.is_dir():
        for item in sorted(out.rglob("*")):
            rel = item.relative_to(out).as_posix()
            safe_path(root, "generated/" + rel)
            if item.is_file():
                existing[rel] = digest(item.read_bytes())
    files = []
    for name in sorted(set(desired) | set(owned)):
        target = safe_path(root, "generated/" + name)
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        after = desired.get(name, "")
        if name not in desired:
            status = "delete" if name in existing else "same"
        elif name not in existing:
            status = "create"
        else:
            status = "same" if before == after else "update"
        if name in existing and status != "same" and owned.get(name) != existing[name]:
            status = "conflict"
        files.append({"path": name, "status": status, "before": before, "after": after})
    token = digest(json.dumps({"d": desired, "e": existing, "o": owned}, sort_keys=True, ensure_ascii=False))
    blocked = any(f["status"] == "conflict" for f in files)
    return {"token": token, "files": files, "blocked": blocked,
            "reason": "generated/ 里有被手改的文件，已阻止覆盖。请把改动移到 src/ 或 board/，或删除这些文件。" if blocked else "", "analysis": info}


def commit(path: str, model: dict, token: str) -> dict:
    root = project_root(path)
    lock = safe_path(root, ".efw/generate.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ServiceError("CONFLICT", "另一个生成操作正在进行；若上次异常退出，请删除 .efw/generate.lock") from exc
    os.close(fd)
    changed: list[tuple[Path, bool, str]] = []
    try:
        current = preview(path, model)
        if not token or current["token"] != token:
            raise ServiceError("CONFLICT", "项目或生成目录在预览之后发生了变化，请重新预览")
        if current["blocked"]:
            raise ServiceError("CONFLICT", current["reason"])
        backup = uuid.uuid4().hex[:10]
        for item in current["files"]:
            if item["status"] == "same":
                continue
            target = safe_path(root, "generated/" + item["path"])
            existed = target.exists()
            if existed:
                atomic_write(safe_path(root, f".efw/backups/{backup}/{item['path']}"), item["before"])
            changed.append((target, existed, item["before"]))
            if item["status"] == "delete":
                target.unlink(missing_ok=True)
            else:
                atomic_write(target, item["after"])
        owned = {i["path"]: digest(i["after"]) for i in current["files"] if i["status"] != "delete" and i["after"]}
        atomic_write(safe_path(root, ".efw/generated.json"), json_text(owned))
        return {"output": str(root / "generated"), "files": [{"path": f["path"], "status": f["status"]} for f in current["files"]]}
    except Exception:
        for target, existed, before in reversed(changed):
            if existed:
                atomic_write(target, before)
            else:
                target.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink(missing_ok=True)
