"""Build, simulate, and flash APIs."""

from __future__ import annotations

from pathlib import Path

from tools.api.capabilities import register_capability
from tools.project.core import load_json, load_project, project_graph_path, project_output_dir, rel_or_abs


register_capability("build.project", "Build a generated project application")
register_capability("simulate.project", "Simulate the project target MCU")
register_capability("flash.project", "Flash a project firmware binary")


def project_chip(project: dict, graph: dict | None = None) -> str:
    chip = str(project.get("chip") or "").strip()
    if chip:
        return chip
    if isinstance(graph, dict):
        chip = str(graph.get("project", {}).get("chip") or "").strip()
        if chip:
            return chip
    board = str(project.get("board_profile") or "").strip()
    return board if board and board != "stm32-basic" else "STM32F407VGT6"


def build_project(project_ref: str | Path, *, chip: str | None = None, build_dir: str | None = None, generate_first: bool = False) -> int:
    path, project = load_project(project_ref)
    graph_path = project_graph_path(path, project)
    graph = load_json(graph_path)
    if generate_first:
        from codegen.cli import main as codegen_main
        result = codegen_main([str(graph_path), "-o", str(project_output_dir(path, project)), "--force"])
        if result != 0:
            return result
    resolved_chip = chip or project_chip(project, graph)
    resolved_dir = build_dir or str(project_output_dir(path, project))
    from tools.compiler.compiler import cmd_build
    return cmd_build(["compile", "--chip", resolved_chip, "--dir", resolved_dir])


def simulate_project(project_ref: str | Path, *, chip: str | None = None, duration: int = 1000) -> int:
    path, project = load_project(project_ref)
    graph = load_json(project_graph_path(path, project))
    from tools.efw import cmd_simulate
    return cmd_simulate(["--chip", chip or project_chip(project, graph), "--duration", str(duration)])


def find_firmware_binary(project_ref: str | Path, explicit: str | None = None) -> Path | None:
    path, project = load_project(project_ref)
    if explicit:
        return rel_or_abs(explicit)
    output_dir = project_output_dir(path, project)
    candidates = sorted(output_dir.glob("**/*.bin")) if output_dir.exists() else []
    if candidates:
        return candidates[0]
    build_dir = output_dir / "build"
    candidates = sorted(build_dir.glob("**/*.bin")) if build_dir.exists() else []
    return candidates[0] if candidates else None


def flash_project(project_ref: str | Path, *, bin_file: str | None = None, port: str | None = None, tool: str = "stlink", erase: bool = False) -> int:
    firmware = find_firmware_binary(project_ref, bin_file)
    if firmware is None:
        raise FileNotFoundError("找不到 .bin 固件；请先 build，或使用 --bin 指定。")
    from tools.efw import cmd_flash
    argv = ["--bin", str(firmware), "--tool", tool]
    if port:
        argv.extend(["--port", port])
    if erase:
        argv.append("--erase")
    return cmd_flash(argv)
