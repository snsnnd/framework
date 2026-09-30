"""Project APIs shared by CLI, Studio, and automation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from tools.api.capabilities import register_capability
from tools.api import graph as graph_api
from tools.project.core import (
    add_recent_project,
    create_project_files,
    display_path,
    iter_project_descriptors,
    load_json,
    load_project,
    load_recent_projects,
    project_graph_path,
    project_output_dir,
    project_slug,
    rel_or_abs,
    remove_recent_project,
    write_json,
)


register_capability("project.create", "Create an EFW project")
register_capability("project.list", "List known EFW projects")
register_capability("project.info", "Read project descriptor summary")
register_capability("project.recent", "List recent EFW projects")
register_capability("project.delete", "Delete a managed EFW project")
register_capability("project.generate", "Generate application from project Graph")
register_capability("project.set", "Edit project descriptor fields")
register_capability("project.rename", "Rename project descriptor")
register_capability("project.clone", "Clone project descriptor and Graph")


def create_project(name: str, *, output_dir: str | Path | None = None, board_profile: str = "stm32-basic", project_dir: str | Path | None = None, chip: str = "", force: bool = False) -> dict[str, Any]:
    descriptor_path, graph_path, descriptor = create_project_files(
        name,
        output_dir=output_dir,
        board_profile=board_profile,
        project_dir=rel_or_abs(project_dir) if project_dir else None,
        chip=chip,
        force=force,
    )
    return {"project_path": descriptor_path, "graph_path": graph_path, "descriptor": descriptor}


def format_path(path: str | Path) -> str:
    return display_path(Path(path))


def resolve_path(path: str | Path) -> Path:
    return rel_or_abs(path)


def list_projects() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in iter_project_descriptors():
        item: dict[str, Any] = {"path": path, "display_path": display_path(path), "readable": False}
        try:
            project = load_json(path)
            item.update({
                "readable": True,
                "name": project.get("name", path.stem),
                "board_profile": project.get("board_profile", "") or "-",
                "graph_path": project.get("graph_path", "") or "-",
            })
        except Exception as exc:  # noqa: BLE001 - callers render unreadable entries.
            item["error"] = str(exc)
        result.append(item)
    return result


def project_info(project_ref: str | Path) -> dict[str, Any]:
    path, project = load_project(project_ref)
    graph_path = project_graph_path(path, project)
    output_dir = project_output_dir(path, project)
    return {
        "path": path,
        "display_path": display_path(path),
        "name": project.get("name", path.stem),
        "graph_path": graph_path,
        "graph_display_path": display_path(graph_path),
        "graph_exists": graph_path.exists(),
        "output_dir": output_dir,
        "output_display_path": display_path(output_dir),
        "board_profile": project.get("board_profile", "-"),
        "chip": project.get("chip", ""),
        "notes": str(project.get("notes", "")).strip(),
        "descriptor": project,
    }


def recent_projects() -> list[dict[str, Any]]:
    return [{"path": item, "exists": rel_or_abs(item).exists()} for item in load_recent_projects()]


def validate_project(project_ref: str | Path) -> dict[str, Any]:
    path, project = load_project(project_ref)
    ctx = graph_api.validate_graph(path)
    add_recent_project(path)
    return {"project_path": path, "project": project, "context": ctx, "graph_path": project_graph_path(path, project)}


def generate_project(project_ref: str | Path, *, output: str | Path | None = None, force: bool = True, dry_run: bool = False) -> int:
    path, project = load_project(project_ref)
    graph_path = project_graph_path(path, project)
    output_dir = rel_or_abs(output) if output else project_output_dir(path, project)
    from codegen.cli import main as codegen_main
    argv = [str(graph_path), "-o", str(output_dir)]
    if force:
        argv.append("--force")
    if dry_run:
        argv.append("--dry-run")
    result = codegen_main(argv)
    if result == 0:
        add_recent_project(path)
    return result


def delete_project(project_ref: str | Path, *, confirmed: bool = False) -> dict[str, Any]:
    path, project = load_project(project_ref)
    if not confirmed:
        return {"deleted": False, "requires_confirmation": True, "project_path": path, "project_dir": path.parent, "name": project.get("name", path.stem)}
    remove_recent_project(path)
    name = project.get("name", path.stem)
    from tools.project.core import PROJECT_ROOT
    if PROJECT_ROOT in path.parents:
        import shutil
        shutil.rmtree(path.parent)
    else:
        path.unlink(missing_ok=True)
    return {"deleted": True, "name": name, "project_path": path}


def set_project_fields(project_ref: str | Path, **fields: Any) -> Path:
    path, project = load_project(project_ref)
    mapping = {
        "name": "name",
        "chip": "chip",
        "board": "board_profile",
        "board_profile": "board_profile",
        "graph": "graph_path",
        "graph_path": "graph_path",
        "output": "output_dir",
        "output_dir": "output_dir",
        "notes": "notes",
    }
    for key, value in fields.items():
        if value is None:
            continue
        target = mapping.get(key, key)
        project[target] = value
    write_json(path, project)
    add_recent_project(path)
    return path


def rename_project(project_ref: str | Path, name: str) -> Path:
    return set_project_fields(project_ref, name=name)


def clone_project(project_ref: str | Path, name: str, *, output: str | Path | None = None, board_profile: str | None = None, project_dir: str | Path | None = None, chip: str | None = None, force: bool = False) -> dict[str, Any]:
    src_path, project = load_project(project_ref)
    source_graph = copy.deepcopy(load_json(project_graph_path(src_path, project)))
    descriptor_path, graph_path, descriptor = create_project_files(
        name,
        graph=source_graph,
        output_dir=output or f"application/generated_{project_slug(name)}",
        board_profile=board_profile or str(project.get("board_profile") or "stm32-basic"),
        project_dir=rel_or_abs(project_dir) if project_dir else None,
        chip=chip or str(project.get("chip") or source_graph.get("project", {}).get("chip") or ""),
        force=force,
    )
    return {"project_path": descriptor_path, "graph_path": graph_path, "descriptor": descriptor}


# Compatibility wrappers for earlier Studio-facing imports.
def load_project_descriptor(project_ref: str | Path) -> tuple[Path, dict[str, Any]]:
    return load_project(project_ref)


def get_project_graph_path(project_ref: str | Path) -> Path:
    return graph_api.graph_path(project_ref)


def get_project_graph_info(project_ref: str | Path) -> dict[str, Any]:
    return graph_api.graph_info(project_ref)


def export_project_graph(project_ref: str | Path, output: str | Path) -> Path:
    return graph_api.export_graph(project_ref, output)


def format_project_graph(project_ref: str | Path) -> Path:
    return graph_api.format_graph(project_ref)


def set_project_graph_value(project_ref: str | Path, dotted_key: str, value: Any) -> Path:
    return graph_api.set_graph_value(project_ref, dotted_key, value)


def reset_project_graph(project_ref: str | Path) -> Path:
    return graph_api.reset_graph(project_ref)
