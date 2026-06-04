"""Template discovery, summaries, and typed-property choices for EFW Studio."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .component_metadata import COMPONENT_METADATA


def _extract_enable_macros(text: str) -> list[str]:
    return sorted(set(__import__("re").findall(r"EFW_ENABLE_[A-Z0-9_]+", text)))


def _annotate_scan_template(template: dict[str, Any], key: str, header: Path, repo_root: Path, library_module: str, callbacks: list[str]) -> None:
    text = header.read_text(encoding="utf-8", errors="ignore")
    template["framework_header"] = header.relative_to(repo_root).as_posix()
    template["library_module"] = library_module
    template["scan_quality"] = "inferred-from-header-path"
    template["callbacks"] = callbacks
    template["includes"] = [template["framework_header"]]
    template["requires_macros"] = _extract_enable_macros(text)
    template["schema_fields"] = sorted(key for key in template if key not in {"id", "type"})
    template["generation"] = "当前 schema 可生成注册 glue；具体业务回调仍由 custom_files/board_adapters 实现。"
    template["scan_warning"] = "路径/头文件元数据推断，尚未解析完整 C AST；复杂依赖请补组件描述文件。"
    metadata = COMPONENT_METADATA.get(key) or COMPONENT_METADATA.get(template.get("type", "")) or {}
    if metadata:
        template.update(copy.deepcopy(metadata))
        template.setdefault("framework_header", header.relative_to(repo_root).as_posix())
        template.setdefault("scan_warning", "使用显式组件 metadata；字段、回调、宏与生成边界来自 metadata。")
    template.setdefault("requires", [])
    template.setdefault("note", f"从框架头文件 {template['framework_header']} 自动扫描得到；字段/回调为 metadata 优先、路径推断兜底，生成时仍会按 schema 校验。")


def discover_framework_templates(node_templates: dict[str, dict[str, Any]], repo_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Scan EFW public headers and expose graph templates for the palette.

    The scan is conservative but not empty: each scanned card records the header,
    inferred library module, callback fields, and generation boundary.  This lets
    the UI show where a card came from without pretending that path-based scans
    are a full C reflection system.
    """
    templates: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    include_root = repo_root / "include" / "efw"
    if not include_root.exists():
        return templates, order

    def add_template(key: str, template: dict[str, Any], header: Path, library_module: str, callbacks: list[str]) -> None:
        if key in templates:
            return
        _annotate_scan_template(template, key, header, repo_root, library_module, callbacks)
        templates[key] = template
        order.append(key)

    def add_metadata_template(key: str, header_rel: str) -> None:
        metadata = COMPONENT_METADATA.get(key)
        if not metadata or key in templates:
            return
        template = copy.deepcopy(metadata)
        header = repo_root / header_rel
        if header.exists():
            _annotate_scan_template(template, key, header, repo_root, template.get("library_module", "framework"), template.get("callbacks", []))
        else:
            template.setdefault("framework_header", header_rel)
        templates[key] = template
        order.append(key)

    add_metadata_template("scan.sensor.custom", "include/efw/device/sensor/custom.h")
    add_metadata_template("scan.actuator.custom", "include/efw/device/actuator.h")
    add_metadata_template("scan.algorithm.pid", "include/efw/algorithm/control/pid.h")
    add_metadata_template("scan.algorithm.custom", "include/efw/algorithm/algorithm.h")

    skip_stems = {"algorithms", "registry", "sensor", "actuator"}
    for header in sorted(include_root.rglob("*.h")):
        rel = header.relative_to(include_root)
        stem = header.stem
        if stem in skip_stems:
            continue
        parts = rel.parts
        if parts[:2] == ("device", "sensor") and stem not in {"line_tracking", "custom"}:
            template = copy.deepcopy(node_templates["sensor.custom"])
            template.update({"id": f"sensor_{stem}", "sensor_type": stem, "read": f"app_sensor_{stem}_read"})
            add_template(f"scan.sensor.{stem}", template, header, "sensor", ["read"])
        elif parts[:2] == ("device", "actuator") and stem not in {"motor"}:
            template = copy.deepcopy(node_templates["actuator.custom"])
            template.update({"id": f"actuator_{stem}", "actuator_type": stem, "write": f"app_actuator_{stem}_write"})
            add_template(f"scan.actuator.{stem}", template, header, "actuator", ["write"])
        elif parts[0] == "algorithm":
            template = copy.deepcopy(node_templates["algorithm.custom"])
            template.update({"id": f"algo_{stem}", "run": f"app_algo_{stem}_run", "algo_type": "EFW_ALGO_CUSTOM"})
            add_template(f"scan.algorithm.{stem}", template, header, "algorithm", ["run"])
        elif parts == ("hal", "hal.h"):
            for hal_type in ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer"]:
                template = copy.deepcopy(node_templates["hal.custom"])
                template.update({"id": f"hal_{hal_type}", "hal_type": hal_type, "init": f"app_hal_{hal_type}_init"})
                add_template(f"scan.hal.{hal_type}", template, header, "hal", ["init", "read", "write", "ioctl"])
        elif parts == ("module", "module.h"):
            template = copy.deepcopy(node_templates["module.custom"])
            template.update({"id": "module_service", "module_type": "EFW_MODULE_SERVICE"})
            add_template("scan.module.service", template, header, "module", ["init", "start", "stop", "poll"])
        elif parts == ("core", "event.h"):
            template = copy.deepcopy(node_templates["event.topic"])
            template.update({"id": "topic_event", "payload_type": "custom"})
            add_template("scan.event.topic", template, header, "event", [])
        elif parts == ("state", "state_machine.h"):
            template = copy.deepcopy(node_templates["state.machine"])
            template.update({"id": "scanned_state_machine"})
            add_template("scan.state.machine", template, header, "state", ["on_enter", "on_update", "on_exit"])
    return templates, order


def node_summary(node: dict[str, Any]) -> str:
    """Return a compact card summary for important node parameters."""
    node_type = node.get("type", "")
    if node_type == "actuator.motor":
        pwm = node.get("pwm", {})
        direction = node.get("dir_pin", {})
        return f"PWM=T{pwm.get('timer')}/CH{pwm.get('channel')} · DIR={direction.get('port')}{direction.get('pin')}"
    if node_type == "hal.gpio_line_input":
        pins = node.get("pins", [])
        first = pins[0] if pins else {}
        return f"channels={node.get('channels')} · first={first.get('port')}{first.get('pin')}"
    if node_type == "project.module":
        inputs = ",".join(node.get("inputs", [])[:2]) if isinstance(node.get("inputs"), list) else ""
        outputs = ",".join(node.get("outputs", [])[:2]) if isinstance(node.get("outputs"), list) else ""
        return f"in=[{inputs}] · out=[{outputs}]" if inputs or outputs else str(node.get("display_name", ""))
    keys_by_type = {
        "algorithm.pid": ["input_type", "output_type", "kp", "ki", "kd"],
        "task.periodic": ["period_ms", "call"],
        "state.machine": ["initial"],
        "state.state": ["machine", "on_update"],
        "state.transition": ["from", "to", "condition", "priority", "timeout_ms"],
        "event.topic": ["topic_id", "payload_type"],
        "event.subscriber": ["topic", "callback"],
        "hal.custom": ["hal_type", "bus_id"],
        "sensor.custom": ["sensor_type", "output_type", "read"],
        "algorithm.custom": ["input_type", "output_type", "run"],
        "processor.custom": ["input_contract", "output_contract", "process"],
        "module.custom": ["input_type", "output_type", "poll"],
        "actuator.custom": ["actuator_type", "hal_name", "write"],
    }
    keys = keys_by_type.get(node_type, ["module", "period_ms", "framework_header"])
    parts = [f"{key}={node.get(key)}" for key in keys if node.get(key) not in (None, "", [])]
    return " · ".join(parts[:3])


def property_choices(graph: dict[str, Any], node: dict[str, Any], key: str, node_templates: dict[str, dict[str, Any]]) -> list[str]:
    """Return selector choices for common reference/type properties."""
    node_type = node.get("type")
    by_type = lambda t: [n.get("id", "") for n in graph.get("nodes", []) if n.get("type") == t]
    if key == "type":
        return sorted({tpl.get("type", name) for name, tpl in node_templates.items()})
    if key == "module":
        return [""] + by_type("project.module")
    if key in {"input", "hal_name"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith("hal.")]
    if key in {"sensor", "source"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith(("sensor.", "processor.", "module."))]
    if key in {"pid", "algorithm"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith("algorithm.")]
    if key in {"left_motor", "right_motor", "target"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith(("actuator.", "processor.", "module."))]
    if key == "topic":
        return [""] + by_type("event.topic")
    if key == "machine":
        return [""] + by_type("state.machine")
    if key == "event_trigger":
        return [""] + [f"topic:{item}" for item in by_type("event.topic")] + ["event:start", "event:stop", "event:error"]
    if key in {"from", "to"} and node_type == "state.transition":
        states = [n.get("id", "") for n in graph.get("nodes", []) if n.get("type") == "state.state" and (not node.get("machine") or n.get("machine") == node.get("machine"))]
        return [""] + states
    if key == "initial" and node_type == "state.machine":
        return [""] + by_type("state.state")
    if key == "hal_type":
        return ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer", "custom"]
    if key == "sensor_type":
        return ["custom", "imu", "encoder", "ultrasonic", "line_tracking"]
    if key == "actuator_type":
        return ["custom", "led", "relay", "servo", "motor"]
    if key == "module_type":
        return ["EFW_MODULE_CUSTOM", "EFW_MODULE_SERVICE", "EFW_MODULE_CONTROL", "EFW_MODULE_COMMS"]
    if key == "algo_type":
        return ["EFW_ALGO_CUSTOM", "EFW_ALGO_PID", "EFW_ALGO_FILTER", "EFW_ALGO_ESTIMATOR"]
    if key == "io_contract":
        return ["custom", "efw_pid", "scalar", "vector", "event"]
    if key in {"input_contract", "output_contract"}:
        custom_types = [str(n.get("name", "")) for n in graph.get("nodes", []) if n.get("type") in {"data.enum", "data.struct"} and n.get("name")]
        return ["", "raw_bytes", "efw_line_tracking_data_t", "efw_pid_input_t", "efw_pid_output_t", "efw_motor_cmd_t", "line_error", "speed_feedback", "control_cmd", "event_payload", "custom"] + custom_types
    if key in {"input_type", "output_type", "payload_type", "data_type"}:
        custom_types = [str(n.get("name", "")) for n in graph.get("nodes", []) if n.get("type") in {"data.enum", "data.struct"} and n.get("name")]
        return ["", "bool", "int", "uint8_t", "uint16_t", "uint32_t", "float", "double", "efw_line_tracking_data_t", "efw_pid_input_t", "efw_pid_output_t", "efw_motor_cmd_t", "struct", "enum", "custom"] + custom_types
    if key in {"anti_windup"}:
        return ["true", "false"]
    return []
