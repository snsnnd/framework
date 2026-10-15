"""Real-device debug APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.api.capabilities import register_capability
from tools.project.core import load_project


register_capability("device.ports", "List serial ports")
register_capability("device.snapshot", "Read one device snapshot")
register_capability("device.schema", "Read device debug schema")
register_capability("device.list", "List device debug points")
register_capability("device.record", "Record device debug stream")
register_capability("device.analyze", "Analyze recorded debug logs")
register_capability("device.perf", "Read LiteTune debug bridge performance counters")
register_capability("device.panel", "Open debug panel")
register_capability("device.transport_template", "Install LiteTune debug transport template")


class DeviceSession:
    """Persistent real-device session for UI/frontends."""

    def __init__(self, *, port: str, baud: int = 115200):
        from tools.debug.collector import DebugCollector

        self._collector = DebugCollector(port=port, baud=baud)
        self._collector.connect()

    def read_snapshot(self) -> dict[str, Any]:
        return self._collector.read_snapshot()

    def read_schema(self) -> dict[str, Any]:
        return self._collector.get_schema()

    def read_debug_points(self) -> list[dict[str, Any]]:
        return self._collector.read_debug_points()

    def disconnect(self) -> None:
        self._collector.disconnect()

    def close(self) -> None:
        self.disconnect()

    def __enter__(self) -> "DeviceSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


class DebugRecording:
    """Recording session wrapper for UI/frontends."""

    def __init__(self, output: str | Path):
        from tools.debug.recorder import DebugRecorder

        self._recorder = DebugRecorder(output)
        self._recorder.start()

    def record_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._recorder.record(snapshot)

    def record_issue(self, issue: dict[str, Any]) -> None:
        self._recorder.record_issue(issue)

    def stop(self) -> dict[str, Any]:
        return self._recorder.stop()


def install_debug_transport_template(output: str | Path, *, protocol: str = "litetune", transport: str = "uart", force: bool = False):
    from tools.debug.transport import install_transport_template
    return install_transport_template(output, protocol=protocol, transport=transport, force=force)


def open_device_session(*, port: str, baud: int = 115200) -> DeviceSession:
    return DeviceSession(port=port, baud=baud)


def start_debug_recording(output: str | Path) -> DebugRecording:
    return DebugRecording(output)


def list_device_ports() -> list[dict[str, Any]]:
    from tools.debug.collector import list_serial_ports
    return list_serial_ports()


def snapshot_device(*, port: str, baud: int = 115200) -> dict[str, Any]:
    from tools.debug.collector import DebugCollector
    with DebugCollector(port=port, baud=baud) as collector:
        return collector.read_snapshot()


def read_device_schema(*, port: str, baud: int = 115200) -> dict[str, Any]:
    from tools.debug.collector import DebugCollector
    with DebugCollector(port=port, baud=baud) as collector:
        return collector.get_schema()


def read_debug_points(*, port: str, baud: int = 115200) -> list[dict[str, Any]]:
    from tools.debug.collector import DebugCollector
    with DebugCollector(port=port, baud=baud) as collector:
        return collector.read_debug_points()


def read_debug_stats(*, port: str, baud: int = 115200) -> dict[str, Any]:
    from tools.debug.collector import DebugCollector
    with DebugCollector(port=port, baud=baud) as collector:
        return collector.read_debug_stats()


def read_debug_perf(*, port: str, baud: int = 115200) -> dict[str, Any]:
    from tools.debug.collector import DebugCollector
    with DebugCollector(port=port, baud=baud) as collector:
        return collector.read_debug_perf()


def record_device(*, port: str, baud: int = 115200, output: str | Path = "debug_log.jsonl", duration: float = 10.0, interval: float = 0.1) -> dict[str, Any]:
    import time
    from tools.debug.collector import DebugCollector
    from tools.debug.recorder import DebugRecorder

    collector = DebugCollector(port=port, baud=baud)
    collector.connect()
    recorder = DebugRecorder(output)
    recorder.start()
    count = 0
    start = time.time()
    try:
        while time.time() - start < duration:
            recorder.record(collector.read_snapshot())
            count += 1
            time.sleep(interval)
    finally:
        stats = recorder.stop()
        collector.disconnect()
    stats["recorded_by"] = "tools.api.device.record_device"
    stats["sample_count"] = count
    return stats


def record_device_count(*, port: str, baud: int = 115200, output: str | Path, interval_ms: int = 100, max_count: int | None = None, expected: str | Path | None = None, verbose: bool = False, show_issues: bool = False) -> dict[str, Any]:
    import signal
    import sys
    import time
    from tools.debug.collector import DebugCollector
    from tools.debug.comparator import DebugComparator
    from tools.debug.recorder import RecordingSession

    collector = DebugCollector(port=port, baud=baud)
    collector.connect()
    comparator = DebugComparator.from_file(expected) if expected else None
    stop = False

    def signal_handler(sig, frame):
        nonlocal stop
        stop = True

    old_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        with RecordingSession(output, comparator=comparator, auto_compare=bool(comparator)) as session:
            interval = interval_ms / 1000.0
            count = 0
            while not stop:
                try:
                    snapshot = collector.read_snapshot()
                    issues = session.process(snapshot)
                    count += 1
                    if verbose:
                        params = snapshot.get("params", {})
                        print(f"[{count}] {len(params)} params", end="")
                        if issues:
                            print(f", {len(issues)} issues", end="")
                        print()
                    if issues and show_issues:
                        for issue in issues:
                            print(f"  {issue['name']}: {issue['detail']}")
                    if max_count and count >= max_count:
                        break
                    time.sleep(interval)
                except Exception as exc:
                    print(f"采集错误: {exc}", file=sys.stderr)
                    time.sleep(1)
            stats = session.stop()
            stats["sample_count"] = count
            return stats
    finally:
        signal.signal(signal.SIGINT, old_handler)
        collector.disconnect()


def analyze_recording(log_file: str | Path, *, action: str = "summary", param: str | None = None, output: str | Path | None = None, limit: int = 100) -> Any:
    from tools.debug.analyzer import DebugAnalyzer
    analyzer = DebugAnalyzer(log_file)
    if action == "summary":
        analyzer.print_summary()
        return None
    if action == "issues":
        issues = analyzer.find_all_issues()
        if param:
            issues = [i for i in issues if i.get("name") == param]
        return issues[:limit]
    if action == "stats":
        return analyzer.get_param_stats(param) if param else analyzer.get_all_param_stats()
    if action == "export":
        if not output:
            raise ValueError("导出操作需要 output")
        analyzer.export_csv(output, params=[param] if param else None)
        return {"output": str(output)}
    if action == "anomalies":
        if not param:
            raise ValueError("异常检测需要 param")
        return analyzer.find_anomalies(param)[:limit]
    raise ValueError(f"未知分析操作: {action}")


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
