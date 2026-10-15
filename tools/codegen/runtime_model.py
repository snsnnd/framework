"""Pure runtime model builders for generated EFW applications."""

from __future__ import annotations

from typing import Any

try:
    from .utils import c_ident, macro_ident, nodes_of
    from .validate import contract_name_for_output
except ImportError:  # pragma: no cover - supports legacy top-level codegen imports
    from codegen.utils import c_ident, macro_ident, nodes_of
    from codegen.validate import contract_name_for_output


def publisher_source_node(ctx: dict[str, Any], publisher: dict[str, Any]):
    source_id = publisher.get("source")
    return ctx.get("nodes_by_id", {}).get(source_id) if source_id else None


def publisher_payload_contract(ctx: dict[str, Any], publisher: dict[str, Any]):
    source_node = publisher_source_node(ctx, publisher)
    if source_node:
        contract = ctx.get("contracts", {}).get(contract_name_for_output(source_node))
        if contract and str(contract.get("c_type") or contract.get("type") or "") not in {"", "custom"}:
            return contract
    topic = ctx.get("nodes_by_id", {}).get(publisher.get("topic"))
    if topic:
        return ctx.get("contracts", {}).get(str(topic.get("id")))
    return None


def publisher_payload_c_type(ctx: dict[str, Any], publisher: dict[str, Any]) -> str:
    contract = publisher_payload_contract(ctx, publisher) or {}
    return str(contract.get("c_type") or contract.get("type") or "custom")


def publisher_payload_size_expr(ctx: dict[str, Any], publisher: dict[str, Any]) -> str:
    contract = publisher_payload_contract(ctx, publisher) or {}
    c_type = str(contract.get("c_type") or contract.get("type") or "")
    size = int(contract.get("size", 0) or 0)
    if c_type and c_type != "custom":
        return f"(uint16_t)sizeof({c_type})"
    if size > 0:
        return f"{size}u"
    return "0u"


def source_cache_c_type(ctx: dict[str, Any], source_id: str) -> str:
    source_node = ctx.get("nodes_by_id", {}).get(source_id)
    if not source_node:
        return "custom"
    contract = ctx.get("contracts", {}).get(contract_name_for_output(source_node), {})
    return str(contract.get("c_type") or contract.get("type") or "custom")


def publisher_event_trigger_match(topic_value: str) -> str:
    return f"topic:{topic_value}"


def modules_of(ctx: dict[str, Any], type_name: str):
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


def publishers_with_auto(ctx: dict[str, Any], module_id: str | None = None):
    items = []
    for item in build_publisher_runtime_model(ctx):
        node = item["node"]
        if item["mode"] == "manual":
            continue
        if module_id is not None and str(node.get("module", "")) != str(module_id):
            continue
        if module_id is None and node.get("module"):
            continue
        items.append(node)
    return items


def source_auto_publishers(ctx: dict[str, Any], source_id: str):
    return [item["node"] for item in build_publisher_runtime_model(ctx) if item["source_id"] == str(source_id) and item["mode"] == "source-auto"]


def state_machines_for_module(ctx: dict[str, Any], module_id: str | None = None):
    items = []
    for node in nodes_of(ctx, "state.machine"):
        if module_id is not None and str(node.get("module", "")) != str(module_id):
            continue
        if module_id is None and node.get("module"):
            continue
        items.append(node)
    return items


def build_state_runtime_model(ctx: dict[str, Any]):
    model = []
    for machine in nodes_of(ctx, "state.machine"):
        machine_id = str(machine["id"])
        states = [node for node in nodes_of(ctx, "state.state") if node.get("machine") == machine_id]
        transitions = [node for node in nodes_of(ctx, "state.transition") if node.get("machine") == machine_id]
        model.append({
            "machine": machine,
            "machine_id": machine_id,
            "ident": c_ident(machine_id),
            "states": states,
            "transitions": transitions,
            "module": str(machine.get("module", "") or ""),
        })
    return model


def build_project_module_runtime_model(ctx: dict[str, Any]):
    publisher_model = build_publisher_runtime_model(ctx)
    state_model = build_state_runtime_model(ctx)
    model = []
    for node in nodes_of(ctx, "project.module"):
        module_id = str(node.get("id", ""))
        model.append({
            "node": node,
            "module_id": module_id,
            "ident": c_ident(module_id),
            "publishers": [item for item in publisher_model if item["stage"] == "module.poll" and str(item["node"].get("module", "")) == module_id and item["mode"] != "manual"],
            "state_machines": [item for item in state_model if item["module"] == module_id],
        })
    return model


def event_topic_id(ctx: dict[str, Any], topic_ref) -> int:
    topic = ctx["nodes_by_id"].get(topic_ref)
    return int(topic.get("topic_id", 0)) if topic else 0


def publisher_mode(publisher: dict[str, Any]) -> str:
    if publisher.get("data_expr") and publisher.get("size_expr"):
        return "expr/size"
    if publisher.get("source"):
        return "source-auto"
    return "manual"


def publisher_stage(publisher: dict[str, Any]) -> str:
    return "module.poll" if publisher.get("module") else "root app_update_1ms"


def publisher_source_kind(ctx: dict[str, Any], publisher: dict[str, Any]) -> str | None:
    source = publisher_source_node(ctx, publisher)
    return str(source.get("type")) if source else None


def publisher_interval_ms(publisher: dict[str, Any]) -> int:
    return int(publisher.get("interval_ms", 0) or 0)


def build_publisher_runtime_model(ctx: dict[str, Any]):
    model = []
    for publisher in nodes_of(ctx, "event.publisher"):
        model.append({
            "node": publisher,
            "id": str(publisher.get("id", "")),
            "ident": c_ident(str(publisher.get("id", ""))),
            "topic_id": event_topic_id(ctx, publisher.get("topic")),
            "mode": publisher_mode(publisher),
            "stage": publisher_stage(publisher),
            "source_kind": publisher_source_kind(ctx, publisher),
            "source_id": str(publisher.get("source", "") or ""),
            "payload_c_type": publisher_payload_c_type(ctx, publisher),
            "payload_size_expr": publisher_payload_size_expr(ctx, publisher),
            "interval_ms": publisher_interval_ms(publisher),
        })
    return model


def build_hal_runtime_model(ctx: dict[str, Any]):
    model = []
    for node in nodes_of(ctx, "hal.gpio_line_input"):
        model.append({"node": node, "kind": "line_input", "ident": c_ident(node["id"]), "macro": macro_ident(node["id"])})
    for node in nodes_of(ctx, "hal.custom"):
        model.append({"node": node, "kind": "custom_hal", "ident": c_ident(node["id"])})
    return model


def build_sensor_runtime_model(ctx: dict[str, Any]):
    model = []
    for node in nodes_of(ctx, "sensor.line_tracking"):
        model.append({"node": node, "kind": "line_sensor", "ident": c_ident(node["id"]), "input_node": ctx["nodes_by_id"][node["input"]]})
    for node in nodes_of(ctx, "sensor.custom"):
        model.append({"node": node, "kind": "custom_sensor", "ident": c_ident(node["id"])})
    return model


def build_actuator_runtime_model(ctx: dict[str, Any]):
    model = []
    for node in nodes_of(ctx, "actuator.motor"):
        model.append({"node": node, "kind": "motor", "ident": c_ident(node["id"]), "macro": macro_ident(node["id"])})
    for node in nodes_of(ctx, "actuator.custom"):
        model.append({"node": node, "kind": "custom_actuator", "ident": c_ident(node["id"])})
    return model


def build_runtime_summary(ctx: dict[str, Any]):
    publisher_model = build_publisher_runtime_model(ctx)
    state_runtime_model = build_state_runtime_model(ctx)
    project_module_runtime_model = build_project_module_runtime_model(ctx)
    hal_runtime_model = build_hal_runtime_model(ctx)
    sensor_runtime_model = build_sensor_runtime_model(ctx)
    actuator_runtime_model = build_actuator_runtime_model(ctx)
    return {
        "publishers": publisher_model,
        "state_machines": state_runtime_model,
        "project_modules": project_module_runtime_model,
        "hal": hal_runtime_model,
        "sensors": sensor_runtime_model,
        "actuators": actuator_runtime_model,
    }
