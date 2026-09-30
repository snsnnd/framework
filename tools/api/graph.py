"""Graph APIs shared by CLI and Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.api.capabilities import register_capability
from tools.project.core import blank_graph, display_path, load_json, load_project, project_graph_path, write_json
from tools.project.operations import analyze_graph_runtime, analyze_graph_runtime_file, generate_graph_application as _generate_graph_application, preview_graph_generation as _preview_graph_generation, validate_graph_data as _validate_graph_data


register_capability("graph.info", "Read project Graph summary")
register_capability("graph.path", "Resolve project Graph path")
register_capability("graph.export", "Export project Graph JSON")
register_capability("graph.format", "Format project Graph JSON")
register_capability("graph.validate", "Validate project Graph")
register_capability("graph.debug", "Analyze Graph runtime flow")
register_capability("graph.preview_generation", "Preview generated application files")
register_capability("graph.generate_application", "Generate application files from Graph")
register_capability("graph.set_value", "Set a Graph JSON value", cli_visible=False)
register_capability("graph.reset", "Reset a project Graph", cli_visible=False)


def graph_path(project_ref: str | Path) -> Path:
    project_path, project = load_project(project_ref)
    return project_graph_path(project_path, project)


def graph_info(project_ref: str | Path) -> dict[str, Any]:
    project_path, project = load_project(project_ref)
    path = project_graph_path(project_path, project)
    graph = load_json(path)
    return {
        "project_path": display_path(project_path),
        "graph_path": display_path(path),
        "project_name": graph.get("project", {}).get("name", project.get("name", "")),
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "flows": len(graph.get("flows", [])),
        "tasks": len(graph.get("tasks", [])),
        "custom_files": len(graph.get("custom_files", [])),
    }


def export_graph(project_ref: str | Path, output: str | Path) -> Path:
    source = graph_path(project_ref)
    output_path = Path(output).expanduser()
    write_json(output_path, load_json(source))
    return output_path


def format_graph(project_ref: str | Path) -> Path:
    path = graph_path(project_ref)
    write_json(path, load_json(path))
    return path


def validate_graph(project_ref: str | Path) -> dict[str, Any]:
    return validate_graph_data(load_json(graph_path(project_ref)))


def validate_graph_data(graph: dict[str, Any]) -> dict[str, Any]:
    return _validate_graph_data(graph)


def debug_graph(project_ref: str | Path, sections: list[str] | None = None) -> tuple[int, str, str]:
    return analyze_graph_runtime_file(graph_path(project_ref), sections)


def debug_graph_data(graph: dict[str, Any], sections: list[str] | None = None) -> tuple[int, str, str]:
    return analyze_graph_runtime(graph, sections)


def preview_graph_generation(graph: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    return _preview_graph_generation(graph, output_dir)


def generate_graph_application(graph: dict[str, Any], output_dir: Path, force: bool = False) -> None:
    _generate_graph_application(graph, output_dir, force=force)


def set_graph_value(project_ref: str | Path, dotted_key: str, value: Any) -> Path:
    path = graph_path(project_ref)
    graph = load_json(path)
    _set_dotted(graph, dotted_key, value)
    write_json(path, graph)
    return path


def reset_graph(project_ref: str | Path) -> Path:
    project_path, project = load_project(project_ref)
    path = project_graph_path(project_path, project)
    graph = blank_graph(str(project.get("name") or "new_efw_project"), str(project.get("board_profile") or "stm32-basic"), str(project.get("chip") or ""))
    write_json(path, graph)
    return path


def parse_json_value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _set_dotted(data: dict[str, Any], key: str, value: Any) -> None:
    parts = [part for part in key.split(".") if part]
    if not parts:
        raise ValueError("key 不能为空")
    current = data
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"{part} 不是 object")
        current = child
    current[parts[-1]] = value
