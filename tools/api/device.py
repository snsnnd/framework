"""Real-device debug APIs."""

from __future__ import annotations

from pathlib import Path

from tools.api.capabilities import register_capability
from tools.project.core import load_project


register_capability("device.ports", "List serial ports")
register_capability("device.snapshot", "Read one device snapshot")
register_capability("device.schema", "Read device debug schema")
register_capability("device.list", "List device debug points")
register_capability("device.record", "Record device debug stream")
register_capability("device.analyze", "Analyze recorded debug logs")
register_capability("device.panel", "Open debug panel")


def run_device_action(project_ref: str | Path, action: str, *, port: str | None = None, baud: int = 115200, output: str | None = None, log_file: str | None = None, interval: int | None = None, max_count: int | None = None, analyze_action: str = "summary") -> int:
    load_project(project_ref)
    from tools.debug.cli import main as debug_main
    argv = [action]
    if action in {"snapshot", "schema", "list", "record", "panel"}:
        if port:
            argv.extend(["--port", port])
        if baud:
            argv.extend(["--baud", str(baud)])
    if action == "record":
        argv.extend(["-o", output or "debug_log.jsonl"])
        if max_count:
            argv.extend(["--max-count", str(max_count)])
        if interval:
            argv.extend(["--interval", str(interval)])
    if action == "analyze":
        argv.append(log_file or output or "debug_log.jsonl")
        argv.extend(["--action", analyze_action])
    return debug_main(argv)
