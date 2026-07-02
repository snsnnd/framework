"""Project descriptor, path, and recent-project helpers for EFW."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / ".efw_projects"
RECENT_FILE = PROJECT_ROOT / "recent.json"
PROJECT_SUFFIX = ".efw_project.json"
PROJECT_SCHEMA_VERSION = 1


def project_slug(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(name).strip()).strip("_")
    return slug or "new_efw_project"


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def rel_or_abs(path_text: str | Path, base: Path | None = None) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return (base or REPO_ROOT) / path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_project() -> dict[str, Any]:
    return {
        "kind": "efw.project",
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": "generic_embedded_app",
        "description": "EFW 项目文件。它保存项目说明、Graph 路径、输出目录和目标板卡配置。",
        "graph_path": "examples/graphs/generic_embedded_app.json",
        "output_dir": "application/generated_generic_embedded_app",
        "board_profile": "stm32-basic",
        "notes": "Edit graph.json, then run `efw project validate` and `efw project generate`.",
        "workflow": [
            "检查项目名、Graph JSON、输出目录和 Board Profile。",
            "编辑卡片、关系和 custom_files。",
            "校验通过后生成 application。",
        ],
    }


def blank_graph(name: str, board_profile: str = "stm32-basic", chip: str = "") -> dict[str, Any]:
    project: dict[str, Any] = {"name": name, "tick_ms": 1}
    if chip:
        project["chip"] = chip
    return {
        "project": project,
        "board": {"profile": board_profile, "pin_plan": []},
        "nodes": [{"id": "app_module", "type": "project.module", "display_name": "应用模块", "description": "项目的第一个模块。"}],
        "edges": [],
        "flows": [],
        "tasks": [],
        "custom_files": [{"path": "app_custom.c", "content": '#include "efw/efw.h"\n'}],
        "ui": {"positions": {"app_module": [40, 40]}},
    }


def default_project_descriptor(name: str, graph_path: Path, output_dir: Path, board_profile: str, chip: str = "") -> dict[str, Any]:
    descriptor = default_project()
    descriptor.update({
        "name": name,
        "description": f"{name} 的 EFW 项目描述文件。",
        "graph_path": display_path(graph_path),
        "output_dir": display_path(output_dir),
        "board_profile": board_profile,
    })
    if chip:
        descriptor["chip"] = chip
    return descriptor


def load_recent_projects() -> list[str]:
    if not RECENT_FILE.exists():
        return []
    try:
        data = load_json(RECENT_FILE)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and str(item).endswith(PROJECT_SUFFIX)]


def save_recent_projects(paths: list[str]) -> None:
    unique: list[str] = []
    for item in paths:
        if item not in unique:
            unique.append(item)
    write_json(RECENT_FILE, unique[:30])


def add_recent_project(path: Path | str) -> None:
    text = display_path(rel_or_abs(path))
    save_recent_projects([text, *[item for item in load_recent_projects() if item != text]])


def remove_recent_project(path: Path | str) -> None:
    text = display_path(rel_or_abs(path))
    save_recent_projects([item for item in load_recent_projects() if item != text and item != str(path)])


def project_dir_for_name(name: str) -> Path:
    return PROJECT_ROOT / project_slug(name)


def descriptor_path_for_name(name: str) -> Path:
    slug = project_slug(name)
    return project_dir_for_name(slug) / f"{slug}{PROJECT_SUFFIX}"


def find_project_descriptor(ref: str | Path) -> Path:
    ref_text = str(ref)
    path = Path(ref_text).expanduser()
    candidates: list[Path] = []
    if path.suffix == ".json" or path.name.endswith(PROJECT_SUFFIX):
        candidates.append(rel_or_abs(path))
    else:
        candidates.extend([
            descriptor_path_for_name(ref_text),
            rel_or_abs(ref_text),
            rel_or_abs(ref_text) / f"{project_slug(ref_text)}{PROJECT_SUFFIX}",
            rel_or_abs(ref_text) / ".efw_project.json",
        ])
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"找不到项目: {ref}")


def load_project(ref: str | Path) -> tuple[Path, dict[str, Any]]:
    path = find_project_descriptor(ref)
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"项目文件不是 JSON object: {path}")
    return path, normalize_project_descriptor(data, path)


def project_graph_path(project_path: Path, project: dict[str, Any]) -> Path:
    graph_path = project.get("graph_path")
    if not graph_path:
        raise ValueError("项目缺少 graph_path")
    raw = Path(str(graph_path)).expanduser()
    if raw.is_absolute():
        return raw
    sibling = project_path.parent / raw
    if sibling.exists():
        return sibling
    return REPO_ROOT / raw


def project_output_dir(_project_path: Path, project: dict[str, Any]) -> Path:
    output_dir = project.get("output_dir")
    if not output_dir:
        raise ValueError("项目缺少 output_dir")
    return rel_or_abs(str(output_dir), REPO_ROOT)


def normalize_project_descriptor(project: dict[str, Any], project_path: Path) -> dict[str, Any]:
    normalized = dict(default_project())
    normalized.update(project)
    sibling_graph = project_path.parent / "graph.json"
    graph_path_text = str(normalized.get("graph_path", ""))
    if sibling_graph.exists() and graph_path_text in {"", "examples/graphs/generic_embedded_app.json"}:
        normalized["graph_path"] = display_path(sibling_graph)
        if not normalized.get("name") or normalized.get("name") == "generic_embedded_app":
            try:
                graph = load_json(sibling_graph)
                normalized["name"] = str(graph.get("project", {}).get("name") or project_path.stem.replace(PROJECT_SUFFIX, ""))
            except (OSError, json.JSONDecodeError):
                normalized["name"] = project_path.stem.replace(PROJECT_SUFFIX, "")
        if not normalized.get("output_dir") or normalized.get("output_dir") == "application/generated_generic_embedded_app":
            normalized["output_dir"] = f"application/generated_{project_slug(str(normalized.get('name', 'efw_project')))}"
    return normalized


def iter_project_descriptors() -> list[Path]:
    paths = set(PROJECT_ROOT.glob(f"**/*{PROJECT_SUFFIX}")) if PROJECT_ROOT.exists() else set()
    examples_dir = REPO_ROOT / "examples"
    if examples_dir.exists():
        paths.update(examples_dir.glob(f"**/*{PROJECT_SUFFIX}"))
    for item in load_recent_projects():
        path = rel_or_abs(item)
        if path.exists() and path.name.endswith(PROJECT_SUFFIX):
            paths.add(path)
    return sorted(paths, key=display_path)


def create_project_files(name: str, graph: dict[str, Any] | None = None, output_dir: str | Path | None = None, board_profile: str = "stm32-basic", project_dir: Path | None = None, chip: str = "", force: bool = False) -> tuple[Path, Path, dict[str, Any]]:
    slug = project_slug(name)
    target_dir = project_dir or project_dir_for_name(slug)
    descriptor_path = target_dir / f"{slug}{PROJECT_SUFFIX}"
    graph_path = target_dir / "graph.json"
    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        raise FileExistsError(f"项目目录已存在且非空: {display_path(target_dir)}")
    graph_data = graph or blank_graph(name, board_profile, chip)
    graph_data.setdefault("project", {})["name"] = name
    if chip:
        graph_data.setdefault("project", {})["chip"] = chip
    graph_data.setdefault("board", {})["profile"] = board_profile
    output_path = rel_or_abs(output_dir or f"application/generated_{slug}")
    descriptor = default_project_descriptor(name, graph_path, output_path, board_profile, chip)
    write_json(graph_path, graph_data)
    write_json(descriptor_path, descriptor)
    add_recent_project(descriptor_path)
    return descriptor_path, graph_path, descriptor
