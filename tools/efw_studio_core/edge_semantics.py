"""Shared graph-edge semantics for UI connections and code generation."""

from __future__ import annotations

from typing import Any, Callable

PORT_RULES = {
    "hal.gpio_line_input": {"out": ["hal"]},
    "hal.custom": {"out": ["hal"]},
    "sensor.line_tracking": {"in": ["hal"], "out": ["sensor"]},
    "sensor.custom": {"in": ["hal"], "out": ["sensor", "event_source"]},
    "algorithm.pid": {"in": ["sensor"], "out": ["algorithm"]},
    "algorithm.custom": {"in": ["sensor"], "out": ["algorithm"]},
    "actuator.motor": {"in": ["control", "motor_pair"], "out": ["motor_pair"]},
    "actuator.custom": {"in": ["hal", "control"]},
    "module.custom": {"in": ["sensor", "algorithm", "event", "logic_call", "module_input"], "out": ["module", "event_source", "module_output"]},
    "task.periodic": {"in": ["module", "flow", "logic_call"]},
    "project.module": {"in": ["module_input"], "out": ["group", "module_output"]},
    "event.topic": {"out": ["topic"]},
    "event.publisher": {"in": ["topic", "event_source"], "out": ["event"]},
    "event.subscriber": {"in": ["topic"], "out": ["event"]},
    "state.machine": {"out": ["state_machine"]},
    "state.state": {"in": ["state_machine", "transition_to"], "out": ["transition_from"]},
    "state.transition": {"in": ["state_machine", "transition_from"], "out": ["transition_to"]},
    "logic.if": {"in": ["event", "sensor", "logic_condition"], "out": ["logic_true", "logic_false", "logic_call"]},
    "logic.loop": {"in": ["logic_condition"], "out": ["logic_body", "logic_call"]},
    "custom.code": {"out": ["code"]},
}

PORT_COLORS = {
    "hal": "#26c6da",
    "sensor": "#66bb6a",
    "algorithm": "#ab47bc",
    "control": "#ec407a",
    "motor_pair": "#ff8a65",
    "module": "#ffb300",
    "module_input": "#b39ddb",
    "module_output": "#9575cd",
    "flow": "#42a5f5",
    "group": "#7e57c2",
    "topic": "#ef5350",
    "event": "#ff7043",
    "event_source": "#ff8a65",
    "state_machine": "#00acc1",
    "transition_from": "#26a69a",
    "transition_to": "#80cbc4",
    "logic_condition": "#d4e157",
    "logic_true": "#c0ca33",
    "logic_false": "#9e9d24",
    "logic_call": "#dce775",
    "logic_body": "#f0f4c3",
    "code": "#90a4ae",
}


def _c_ident_fallback(value: Any) -> str:
    text = str(value or "node")
    result = []
    for index, ch in enumerate(text):
        if ch == "_" or ch.isalnum():
            result.append(ch)
        else:
            result.append("_")
    joined = "".join(result) or "node"
    if joined[0].isdigit():
        joined = "_" + joined
    return joined


def can_connect_ports(src: dict[str, Any], dst: dict[str, Any], from_port: str | None = None, to_port: str | None = None) -> bool:
    """Return whether a visual port connection has a known graph semantic."""
    if from_port and to_port:
        compatible = {
            ("hal", "hal"),
            ("sensor", "sensor"),
            ("sensor", "logic_condition"),
            ("sensor", "event_source"),
            ("algorithm", "algorithm"),
            ("motor_pair", "motor_pair"),
            ("control", "control"),
            ("module", "module"),
            ("module", "logic_call"),
            ("module_output", "module_input"),
            ("group", "module_input"),
            ("group", "hal"),
            ("group", "sensor"),
            ("group", "algorithm"),
            ("group", "control"),
            ("group", "module"),
            ("group", "topic"),
            ("topic", "topic"),
            ("event_source", "event_source"),
            ("event", "event"),
            ("event", "logic_condition"),
            ("state_machine", "state_machine"),
            ("state_machine", "transition_from"),
            ("transition_from", "transition_from"),
            ("transition_to", "transition_to"),
            ("logic_call", "logic_call"),
            ("logic_true", "logic_call"),
            ("logic_false", "logic_call"),
            ("logic_body", "logic_call"),
            ("code", "hal"),
            ("code", "sensor"),
            ("code", "algorithm"),
            ("code", "module"),
            ("code", "control"),
        }
        if (from_port, to_port) not in compatible:
            return False
    return pair_has_semantics(src, dst)


def pair_has_semantics(src: dict[str, Any], dst: dict[str, Any]) -> bool:
    src_type = src.get("type")
    dst_type = dst.get("type")
    return (
        (src_type == "hal.gpio_line_input" and dst_type == "sensor.line_tracking")
        or (src_type == "hal.custom" and dst_type in {"sensor.custom", "actuator.custom"})
        or (src_type == "project.module" and dst_type != "project.module")
        or (src_type == "project.module" and dst_type == "project.module")
        or (src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"})
        or (src_type in {"module.custom", "sensor.custom", "sensor.line_tracking"} and dst_type == "event.publisher")
        or (src_type == "event.subscriber" and dst_type == "module.custom")
        or (src_type == "state.machine" and dst_type in {"state.state", "state.transition"})
        or (src_type == "state.state" and dst_type == "state.transition")
        or (src_type == "state.transition" and dst_type == "state.state")
        or (src_type in {"logic.if", "logic.loop"} and dst_type in {"task.periodic", "module.custom"})
        or (src_type == "sensor.line_tracking" and dst_type in {"algorithm.pid", "algorithm.custom"})
        or (src_type == "actuator.motor" and dst_type == "actuator.motor")
        or (src_type == "custom.code" and dst_type in {"sensor.custom", "algorithm.custom", "module.custom", "actuator.custom", "hal.custom", "task.periodic"})
    )


def apply_pair_semantics(src: dict[str, Any], dst: dict[str, Any], graph: dict[str, Any] | None = None, c_ident_func: Callable[[Any], str] | None = None, overwrite: bool = True) -> bool:
    """Apply the same semantic edge rules used by both UI and codegen."""
    c_ident = c_ident_func or _c_ident_fallback

    def set_field(node: dict[str, Any], key: str, value: Any) -> None:
        if overwrite or node.get(key) in (None, "", []):
            node[key] = value

    src_type = src.get("type")
    dst_type = dst.get("type")
    if src_type == "hal.gpio_line_input" and dst_type == "sensor.line_tracking":
        set_field(dst, "input", src.get("id"))
        return True
    if src_type == "hal.custom" and dst_type in {"sensor.custom", "actuator.custom"}:
        set_field(dst, "hal_name", src.get("id"))
        return True
    if src_type == "project.module" and dst_type != "project.module":
        set_field(dst, "module", src.get("id"))
        return True
    if src_type == "project.module" and dst_type == "project.module":
        set_field(dst, "parent", src.get("id"))
        return True
    if src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"}:
        set_field(dst, "topic", src.get("id"))
        return True
    if src_type in {"module.custom", "sensor.custom", "sensor.line_tracking"} and dst_type == "event.publisher":
        set_field(dst, "source", src.get("id"))
        return True
    if src_type == "event.subscriber" and dst_type == "module.custom":
        set_field(src, "target", dst.get("id"))
        return True
    if src_type == "state.machine" and dst_type in {"state.state", "state.transition"}:
        set_field(dst, "machine", src.get("id"))
        return True
    if src_type == "state.state" and dst_type == "state.transition":
        set_field(dst, "from", src.get("id"))
        set_field(dst, "machine", src.get("machine") or dst.get("machine"))
        return True
    if src_type == "state.transition" and dst_type == "state.state":
        set_field(src, "to", dst.get("id"))
        set_field(src, "machine", dst.get("machine") or src.get("machine"))
        return True
    if src_type in {"logic.if", "logic.loop"} and dst_type in {"task.periodic", "module.custom"}:
        set_field(dst, "call", f"app_logic_{c_ident(src.get('id', 'logic'))}")
        return True
    if src_type == "sensor.line_tracking" and dst_type in {"algorithm.pid", "algorithm.custom"}:
        if graph is not None:
            flow_id = f"{src.get('id')}_flow"
            flows = graph.setdefault("flows", [])
            existing = next((flow for flow in flows if flow.get("id") == flow_id), None)
            if existing is None:
                existing = {"id": flow_id, "type": "control.line_follower", "period_ms": graph.get("project", {}).get("tick_ms", 1)}
                flows.append(existing)
            set_field(existing, "sensor", src.get("id"))
            set_field(existing, "pid", dst.get("id"))
            if dst_type == "algorithm.custom":
                set_field(dst, "io_contract", "efw_pid")
            motors = [node for node in graph.get("nodes", []) if node.get("type") == "actuator.motor"]
            if len(motors) >= 2:
                existing.setdefault("left_motor", motors[0].get("id"))
                existing.setdefault("right_motor", motors[1].get("id"))
            input_node = next((node for node in graph.get("nodes", []) if node.get("id") == src.get("input")), None)
            channels = int(input_node.get("channels", 5)) if input_node else 5
            existing.setdefault("weights", [float(i) - (channels - 1) / 2.0 for i in range(channels)])
        return True
    if src_type == "actuator.motor" and dst_type == "actuator.motor":
        if graph is not None:
            flows = graph.setdefault("flows", [])
            existing = flows[-1] if flows else {"id": "line_follower", "type": "control.line_follower"}
            if not flows:
                flows.append(existing)
            set_field(existing, "left_motor", src.get("id"))
            set_field(existing, "right_motor", dst.get("id"))
        return True
    if src_type == "custom.code" and dst_type in {"sensor.custom", "algorithm.custom", "module.custom", "actuator.custom", "hal.custom", "task.periodic"}:
        return True
    return False
