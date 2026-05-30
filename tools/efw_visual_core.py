#!/usr/bin/env python3
"""Pure helper logic for the EFW visual tools.

This module deliberately avoids PyQt imports.  UI modules can import these
helpers for palette discovery, property choices, and card summaries without
mixing graph/model logic into widget code.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


def discover_framework_templates(node_templates: dict[str, dict[str, Any]], repo_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Scan EFW public headers and expose graph templates for the palette.

    The scan is intentionally conservative: it only creates templates that can
    be represented by the current generator schema, and it records the source
    header so users can see which framework API the card came from.
    """
    templates: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    include_root = repo_root / "include" / "efw"
    if not include_root.exists():
        return templates, order

    def add_template(key: str, template: dict[str, Any], header: Path) -> None:
        if key in templates:
            return
        template["framework_header"] = header.relative_to(repo_root).as_posix()
        template.setdefault("note", f"从框架头文件 {template['framework_header']} 自动扫描得到；生成时仍会按当前 schema 校验回调。")
        templates[key] = template
        order.append(key)

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
            add_template(f"scan.sensor.{stem}", template, header)
        elif parts[:2] == ("device", "actuator") and stem not in {"motor"}:
            template = copy.deepcopy(node_templates["actuator.custom"])
            template.update({"id": f"actuator_{stem}", "actuator_type": stem, "write": f"app_actuator_{stem}_write"})
            add_template(f"scan.actuator.{stem}", template, header)
        elif parts[0] == "algorithm":
            template = copy.deepcopy(node_templates["algorithm.custom"])
            template.update({"id": f"algo_{stem}", "run": f"app_algo_{stem}_run", "algo_type": "EFW_ALGO_CUSTOM"})
            add_template(f"scan.algorithm.{stem}", template, header)
        elif parts == ("hal", "hal.h"):
            for hal_type in ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer"]:
                template = copy.deepcopy(node_templates["hal.custom"])
                template.update({"id": f"hal_{hal_type}", "hal_type": hal_type, "init": f"app_hal_{hal_type}_init"})
                add_template(f"scan.hal.{hal_type}", template, header)
        elif parts == ("module", "module.h"):
            template = copy.deepcopy(node_templates["module.custom"])
            template.update({"id": "module_service", "module_type": "EFW_MODULE_SERVICE"})
            add_template("scan.module.service", template, header)
        elif parts == ("core", "event.h"):
            template = copy.deepcopy(node_templates["event.topic"])
            template.update({"id": "topic_event", "payload_type": "custom"})
            add_template("scan.event.topic", template, header)
        elif parts == ("state", "state_machine.h"):
            template = copy.deepcopy(node_templates["state.machine"])
            template.update({"id": "scanned_state_machine"})
            add_template("scan.state.machine", template, header)
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
    keys_by_type = {
        "algorithm.pid": ["kp", "ki", "kd", "out_min", "out_max"],
        "task.periodic": ["period_ms", "call"],
        "state.transition": ["from", "to", "condition"],
        "logic.if": ["condition", "then", "else"],
        "logic.loop": ["condition", "body", "max_iterations"],
        "event.topic": ["topic_id", "payload_type"],
        "event.subscriber": ["topic", "callback"],
        "project.module": ["display_name"],
        "hal.custom": ["hal_type", "bus_id"],
        "sensor.custom": ["sensor_type", "hal_name", "read"],
        "actuator.custom": ["actuator_type", "hal_name", "write"],
    }
    keys = keys_by_type.get(node_type, ["module", "period_ms"])
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
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith(("sensor.", "module."))]
    if key in {"pid", "algorithm"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith("algorithm.")]
    if key in {"left_motor", "right_motor", "target"}:
        return [""] + [n.get("id", "") for n in graph.get("nodes", []) if str(n.get("type", "")).startswith(("actuator.", "module."))]
    if key == "topic":
        return [""] + by_type("event.topic")
    if key == "machine":
        return [""] + by_type("state.machine")
    if key in {"from", "to"} and node_type == "state.transition":
        states = [n.get("id", "") for n in graph.get("nodes", []) if n.get("type") == "state.state" and (not node.get("machine") or n.get("machine") == node.get("machine"))]
        return [""] + states
    if key == "hal_type":
        return ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer", "custom"]
    if key == "sensor_type":
        return ["custom", "imu", "encoder", "ultrasonic", "line_tracking"]
    if key == "actuator_type":
        return ["custom", "led", "relay", "servo", "motor"]
    if key == "loop":
        return ["while", "for"]
    return []
