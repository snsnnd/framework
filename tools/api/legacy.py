"""Legacy CLI-compatible project actions kept out of tools/efw.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def design_graph_for_chip(chip: str, output: str | Path) -> dict[str, Any]:
    from tools.simulator.chip_db import get_chip_database

    db = get_chip_database()
    chip_data = db.load_chip(chip)
    if not chip_data:
        raise ValueError(f"未找到芯片: {chip}")

    config: dict[str, Any] = {
        "project": {"name": chip.lower().replace(" ", "_"), "chip": chip, "tick_ms": 1},
        "board": {"profile": chip_data.get("board", ""), "pin_plan": []},
        "nodes": [{"id": "app_module", "type": "project.module", "display_name": "应用模块", "description": f"{chip} 的默认应用模块。"}],
        "edges": [],
        "flows": [],
        "tasks": [],
        "custom_files": [],
        "metadata": {"kind": "efw.graph", "schema_version": 1},
        "chip_data": {
            "family": chip_data.get("family"),
            "core": chip_data.get("core"),
            "clock_mhz": chip_data.get("frequency_mhz"),
            "flash_kb": chip_data.get("flash_kb"),
            "ram_kb": chip_data.get("ram_kb"),
            "gpio_pins": chip_data.get("gpio_pins", []),
            "peripherals": chip_data.get("peripherals", {}),
        },
        "name": chip.lower().replace(" ", "_"),
        "chip": chip,
        "family": chip_data.get("family"),
        "core": chip_data.get("core"),
        "clock_mhz": chip_data.get("frequency_mhz"),
        "flash_kb": chip_data.get("flash_kb"),
        "ram_kb": chip_data.get("ram_kb"),
        "gpio_pins": chip_data.get("gpio_pins", []),
        "peripherals": chip_data.get("peripherals", {}),
        "components": [],
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config


def resolve_graph_path(config_path: str | Path, config: dict[str, Any] | None = None) -> Path:
    path = Path(config_path)
    if config is None:
        config = json.loads(path.read_text(encoding="utf-8"))
    if "nodes" in config and "project" in config:
        return path
    graph_path = config.get("graph_path")
    if graph_path:
        resolved = Path(graph_path)
        return resolved if resolved.is_absolute() else path.parent / resolved
    raise ValueError("输入不是 Graph JSON，也没有 graph_path；请先运行 design 生成 graph 或直接传入 graph.json")


def generate_from_config(config_path: str | Path, output: str | Path, *, force: bool = True, dry_run: bool = False) -> int:
    from tools.api.project import generate_project
    from codegen.cli import main as codegen_main

    path = Path(config_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if "graph_path" in config and "nodes" not in config:
        try:
            return generate_project(path, output=output, force=force, dry_run=dry_run)
        except Exception:
            pass
    graph_path = resolve_graph_path(path, config)
    argv = [str(graph_path), "-o", str(output)]
    if force:
        argv.append("--force")
    if dry_run:
        argv.append("--dry-run")
    return codegen_main(argv)


def simulate_chip(chip: str, *, duration: int = 1000, progress: bool = True,
                  workload: str = "idle") -> dict[str, Any]:
    import time
    from tools.simulator.core import MCUSimulator
    from tools.simulator.perf import PerformanceMonitor

    mcu = MCUSimulator.from_chip(chip)

    if workload == "efw":
        # calibrated EFW framework model (measured on CT117E-M4 silicon)
        from tools.simulator.efw_model import EFWWorkload, simulate_efw
        wl = EFWWorkload(
            registry_entries=8,
            lookups_per_ms=2,
            pid_runs_per_ms=1,       # 1kHz control loop
            publishes_per_ms=1,
            pub_subscribers=4,
            queue_ops_per_ms=1,
            scheduler_tasks=4,
        )
        report = simulate_efw(mcu, wl, duration)
        report["chip"] = chip
        return report

    monitor = PerformanceMonitor()
    monitor.start()
    cycles_per_ms = mcu.clock.sysclk_hz // 1000
    start_time = time.time()
    for i in range(duration):
        monitor.begin_frame()
        mcu.tick(cycles_per_ms)
        monitor.end_frame(cycles=cycles_per_ms, instructions=cycles_per_ms)
        if progress and (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  进度: {i + 1}/{duration} ({elapsed:.1f}s)")
    elapsed = time.time() - start_time
    return {
        "chip": chip,
        "sysclk_hz": mcu.clock.sysclk_hz,
        "duration_ms": duration,
        "elapsed_seconds": elapsed,
        "speed_x": (duration / 1000 / elapsed) if elapsed > 0 else 0,
        "total_cycles": monitor._total_cycles,
    }
