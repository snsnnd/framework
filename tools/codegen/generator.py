#!/usr/bin/env python3
"""Render and write EFW application code from a validated graph.

The generator is still intentionally small, but it is no longer tied to a single
line-follower instance.  It supports multiple line-follower flows, periodic
custom tasks, custom sensors/algorithms/modules whose implementation lives in
`custom_files`, and generated application glue that schedules all configured
flows from a 1 ms tick.
"""

import hashlib
import json
import re
from string import Template
from pathlib import Path
from typing import Any

from codegen.utils import c_ident, macro_ident, c_str, c_float, c_bool, require, nodes_of, number_or_default
from codegen.validate import BUILTIN_CONTRACTS, contract_name_for_output, validate_graph


def graph_edges_of(ctx, kinds=None):
    selected = []
    kind_set = set(kinds or [])
    for edge in ctx.get("edges", []):
        if not isinstance(edge, dict):
            continue
        if kinds and edge.get("kind", "generic") not in kind_set:
            continue
        src = ctx["nodes_by_id"].get(edge.get("from"))
        dst = ctx["nodes_by_id"].get(edge.get("to"))
        if src and dst:
            selected.append((edge, src, dst))
    return selected


def dataflow_edges(ctx):
    return graph_edges_of(ctx, {"data_flow", "control_flow"})


def dataflow_paths(ctx):
    """Return executable Sensor -> Processor/Algorithm -> Actuator paths.

    The graph can still document module interfaces and event relations, but only
    concrete runtime-capable nodes are scheduled here.  A path starts at a sensor,
    may pass through processor.custom and algorithm.* nodes, and may optionally
    terminate at an actuator.  Branching creates one executable path per branch.
    """
    if "runtime_dataflows" in ctx:
        return [list(path) for path in ctx.get("runtime_dataflows", [])]
    runtime_types = {"sensor.custom", "sensor.line_tracking", "processor.custom", "algorithm.pid", "algorithm.custom", "actuator.motor", "actuator.custom"}
    adjacency = {}
    incoming = {}
    for _edge, src, dst in dataflow_edges(ctx):
        if src.get("type") not in runtime_types or dst.get("type") not in runtime_types:
            continue
        adjacency.setdefault(src["id"], []).append(dst["id"])
        incoming.setdefault(dst["id"], []).append(src["id"])
    starts = [node["id"] for node in ctx["nodes"] if node.get("type") in {"sensor.custom", "sensor.line_tracking"} and node.get("id") in adjacency]
    paths = []

    def walk(node_id, path, seen):
        next_ids = [item for item in adjacency.get(node_id, []) if item not in seen]
        if not next_ids:
            if len(path) > 1:
                paths.append(path[:])
            return
        for next_id in next_ids:
            walk(next_id, path + [next_id], seen | {next_id})

    for start in starts:
        walk(start, [start], {start})
    # Keep longest/leaf paths only; prefixes are implementation details of a longer executable chain.
    unique = []
    seen_keys = set()
    for path in paths:
        key = tuple(path)
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(path)
    return unique


def dataflow_period_ms(ctx, path):
    tick_ms = int(ctx["project"].get("tick_ms", 1))
    periods = [int(ctx["nodes_by_id"][node_id].get("period_ms", tick_ms)) for node_id in path]
    return max(periods or [tick_ms])


def dataflow_buffer_size(ctx):
    configured = int(ctx["project"].get("dataflow_buffer_size", 0) or 0)
    contract_sizes = [int(contract.get("size", 0) or 0) for contract in ctx.get("contracts", {}).values()]
    return max([configured, 64] + contract_sizes)


def publisher_source_node(ctx, publisher):
    source_id = publisher.get("source")
    return ctx.get("nodes_by_id", {}).get(source_id) if source_id else None


def publisher_payload_contract(ctx, publisher):
    source_node = publisher_source_node(ctx, publisher)
    if source_node:
        contract = ctx.get("contracts", {}).get(contract_name_for_output(source_node))
        if contract and str(contract.get("c_type") or contract.get("type") or "") not in {"", "custom"}:
            return contract
    topic = ctx.get("nodes_by_id", {}).get(publisher.get("topic"))
    if topic:
        return ctx.get("contracts", {}).get(str(topic.get("id")))
    return None


def publisher_payload_c_type(ctx, publisher):
    contract = publisher_payload_contract(ctx, publisher) or {}
    return str(contract.get("c_type") or contract.get("type") or "custom")


def publisher_payload_size_expr(ctx, publisher):
    contract = publisher_payload_contract(ctx, publisher) or {}
    c_type = str(contract.get("c_type") or contract.get("type") or "")
    size = int(contract.get("size", 0) or 0)
    if c_type and c_type != "custom":
        return f"(uint16_t)sizeof({c_type})"
    if size > 0:
        return f"{size}u"
    return "0u"


def source_cache_c_type(ctx, source_id: str):
    source_node = ctx.get("nodes_by_id", {}).get(source_id)
    if not source_node:
        return "custom"
    contract = ctx.get("contracts", {}).get(contract_name_for_output(source_node), {})
    return str(contract.get("c_type") or contract.get("type") or "custom")


def publisher_event_trigger_match(topic_value: str) -> str:
    return f"topic:{topic_value}"


def modules_of(ctx, type_name):
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


def publishers_with_auto(ctx, module_id: str | None = None):
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


def source_auto_publishers(ctx, source_id: str):
    return [item["node"] for item in build_publisher_runtime_model(ctx) if item["source_id"] == str(source_id) and item["mode"] == "source-auto"]


def state_machines_for_module(ctx, module_id: str | None = None):
    items = []
    for node in nodes_of(ctx, "state.machine"):
        if module_id is not None and str(node.get("module", "")) != str(module_id):
            continue
        if module_id is None and node.get("module"):
            continue
        items.append(node)
    return items


def build_state_runtime_model(ctx):
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


def build_project_module_runtime_model(ctx):
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


def build_runtime_summary(ctx):
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


def render_project_module_shells(module_runtime_model):
    parts = []
    for module_runtime in module_runtime_model:
        node = module_runtime["node"]
        ident = module_runtime["ident"]
        parts.append(f"static efw_status_t app_project_module_{ident}_poll(void *ctx) {{\n    efw_status_t s;\n    EFW_UNUSED(ctx);\n")
        for publisher in module_runtime["publishers"]:
            parts.append(f"    s = app_publish_{publisher['ident']}_auto();\n    if (s != EFW_OK) return s;\n")
        for machine in module_runtime["state_machines"]:
            parts.append(f"    s = app_sm_{machine['ident']}_tick();\n    if (s != EFW_OK) return s;\n")
        parts.append("    return EFW_OK;\n}\n\n")
        parts.append(f"""static efw_module_ops_t g_{ident}_project_module = {{
    .name = {c_str(node['id'])},
    .type = EFW_MODULE_APP,
    .ctx = 0,
    .poll = app_project_module_{ident}_poll,
}};

""")
    return "".join(parts)


def render_project_module_registrations(module_runtime_model):
    return "".join(
        f"    s = efw_module_register(&g_{item['ident']}_project_module);\n    if (s != EFW_OK) return s;\n"
        for item in module_runtime_model
    )


def render_state_api_declarations(state_runtime_model):
    lines = []
    for machine_runtime in state_runtime_model:
        ident = machine_runtime["ident"]
        lines.append(f"efw_status_t app_sm_{ident}_tick(void);\n")
        lines.append(f"efw_status_t app_sm_{ident}_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);\n")
        lines.append(f"efw_status_t app_sm_{ident}_transition_to(const char *state_name);\n")
        lines.append(f"const char *app_sm_{ident}_current_state(void);\n")
    return "".join(lines)


def render_state_machine_bundle(machine_runtime):
    parts = []
    mid = machine_runtime["machine_id"]
    m_ident = machine_runtime["ident"]
    states = machine_runtime["states"]
    index = {state["id"]: i for i, state in enumerate(states)}
    for state in states:
        s_ident = c_ident(state["id"])
        parts.append(f"static efw_state_machine_ops_t g_state_{s_ident} = {{\n")
        parts.append(f"    .name = {c_str(state['id'])},\n    .ctx = 0,\n")
        parts.append(f"    .on_enter = {c_ident(state['on_enter']) if state.get('on_enter') else '0'},\n")
        parts.append(f"    .on_tick = {c_ident(state['on_update']) if state.get('on_update') else 'app_noop_status'},\n")
        parts.append(f"    .on_exit = {c_ident(state['on_exit']) if state.get('on_exit') else '0'},\n}};\n")
    parts.append(f"static efw_state_machine_ops_t *g_{m_ident}_states[] = {{ {', '.join('&g_state_' + c_ident(s['id']) for s in states)} }};\n")
    parts.append(f"static const char *g_{m_ident}_state_names[] = {{ {', '.join(c_str(s['id']) for s in states)} }};\n")
    initial = machine_runtime["machine"].get("initial") or (states[0]["id"] if states else "")
    parts.append(f"static uint8_t g_{m_ident}_current = {index.get(initial, 0)}u;\n")
    parts.append(f"static uint32_t g_{m_ident}_entered_ms;\n")
    parts.append(f"static efw_status_t app_sm_{m_ident}_transition_index(uint8_t to_idx, efw_status_t (*action)(void)) {{\n    efw_status_t s;\n    if (to_idx >= {len(states)}u) return EFW_ERR_INVALID;\n")
    if states:
        parts.append(f"    if (g_{m_ident}_states[g_{m_ident}_current]->on_exit) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_exit(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
    parts.append("    if (action) { s = action(); if (s != EFW_OK) return s; }\n")
    parts.append(f"    g_{m_ident}_current = to_idx;\n    g_{m_ident}_entered_ms = g_app_elapsed_ms;\n")
    if states:
        parts.append(f"    if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
    parts.append("    return EFW_OK;\n}\n")
    parts.append(f"static efw_status_t app_{m_ident}_register(void) {{\n    efw_status_t s;\n")
    for state in states:
        parts.append(f"    s = efw_sm_register(&g_state_{c_ident(state['id'])});\n    if (s != EFW_OK) return s;\n")
    if states:
        parts.append(f"    if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
        parts.append(f"    g_{m_ident}_entered_ms = g_app_elapsed_ms;\n")
    parts.append("    return EFW_OK;\n}\n")
    parts.append(f"const char *app_sm_{m_ident}_current_state(void) {{\n    return g_{m_ident}_state_names[g_{m_ident}_current];\n}}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_transition_to(const char *state_name) {{\n")
    for state in states:
        parts.append(f"    if (app_bootstrap_name_eq(state_name, {c_str(state['id'])})) return app_sm_{m_ident}_transition_index({index.get(state['id'], 0)}u, 0);\n")
    parts.append("    return EFW_ERR_NOT_FOUND;\n}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size) {{\n    efw_status_t s;\n    EFW_UNUSED(data);\n    EFW_UNUSED(size);\n")
    if states:
        ordered_transitions = sorted(machine_runtime["transitions"], key=lambda item: int(item.get("priority", 0)))
        eventful = [transition for transition in ordered_transitions if str(transition.get("event_trigger", "")).strip()]
        for transition in eventful:
            from_idx = index.get(transition.get("from"), 0)
            to_idx = index.get(transition.get("to"), 0)
            cond = c_ident(transition["condition"]) + "()"
            action = c_ident(transition["action"]) if transition.get("action") else "0"
            parts.append(f"    if (g_{m_ident}_current == {from_idx}u && app_bootstrap_event_matches({c_str(transition.get('event_trigger'))}, event_name, topic_id) && ({cond})) return app_sm_{m_ident}_transition_index({to_idx}u, {action});\n")
    parts.append("    return EFW_ERR_NOT_FOUND;\n}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_tick(void) {{\n    efw_status_t s;\n")
    if states:
        parts.append(f"    s = g_{m_ident}_states[g_{m_ident}_current]->on_tick(g_{m_ident}_states[g_{m_ident}_current]->ctx);\n    if (s != EFW_OK) return s;\n")
        ordered_transitions = sorted(machine_runtime["transitions"], key=lambda item: int(item.get("priority", 0)))
        for transition in ordered_transitions:
            if str(transition.get("event_trigger", "")).strip():
                continue
            cond_parts = [c_ident(transition["condition"]) + "()"]
            timeout_ms = int(transition.get("timeout_ms", 0))
            if timeout_ms > 0:
                cond_parts.append(f"((g_app_elapsed_ms - g_{m_ident}_entered_ms) >= {timeout_ms}u)")
            cond = " && ".join(cond_parts)
            from_idx = index.get(transition.get("from"), 0)
            to_idx = index.get(transition.get("to"), 0)
            action = c_ident(transition["action"]) if transition.get("action") else "0"
            parts.append(f"    if (g_{m_ident}_current == {from_idx}u && ({cond})) {{\n")
            parts.append(f"        return app_sm_{m_ident}_transition_index({to_idx}u, {action});\n    }}\n")
    parts.append("    return EFW_OK;\n}\n\n")
    return "".join(parts)


def render_publisher_runtime(ctx, publisher_model):
    parts = []
    for source_id in sorted({item["source_id"] for item in publisher_model if item["source_id"]}):
        ident = c_ident(source_id)
        parts.append(f"static app_dataflow_buffer_t g_{ident}_pub_cache;\n")
        parts.append(f"static uint16_t g_{ident}_pub_cache_size;\n")
        parts.append(f"static uint8_t g_{ident}_pub_cache_valid;\n")
        parts.append(f"static void app_cache_source_{ident}(const void *data, uint16_t size) {{\n")
        parts.append("    if (!data || size == 0u) return;\n")
        parts.append("    if (size > APP_DATAFLOW_BUFFER_SIZE) size = APP_DATAFLOW_BUFFER_SIZE;\n")
        parts.append(f"    memcpy(g_{ident}_pub_cache.raw, data, size);\n")
        parts.append(f"    g_{ident}_pub_cache_size = size;\n")
        parts.append(f"    g_{ident}_pub_cache_valid = 1u;\n")
        parts.append("}\n")
    for item in publisher_model:
        ident = item["ident"]
        parts.append(f"static app_dataflow_buffer_t g_{ident}_last_pub;\n")
        parts.append(f"static uint16_t g_{ident}_last_pub_size;\n")
        parts.append(f"static uint8_t g_{ident}_last_pub_valid;\n")
        parts.append(f"static uint32_t g_{ident}_last_pub_ms;\n")
        parts.append(f"static efw_status_t app_publish_{ident}_auto_commit(uint16_t topic_id, const void *data, uint16_t size, uint32_t min_interval_ms) {{\n")
        parts.append("    if (!data || size == 0u) return EFW_ERR_INVALID;\n")
        parts.append(f"    if (min_interval_ms > 0u && (g_app_elapsed_ms - g_{ident}_last_pub_ms) < min_interval_ms) return EFW_OK;\n")
        parts.append(f"    if (g_{ident}_last_pub_valid && g_{ident}_last_pub_size == size && size <= APP_DATAFLOW_BUFFER_SIZE && memcmp(g_{ident}_last_pub.raw, data, size) == 0) return EFW_OK;\n")
        parts.append(f"    if (size <= APP_DATAFLOW_BUFFER_SIZE) memcpy(g_{ident}_last_pub.raw, data, size);\n")
        parts.append(f"    g_{ident}_last_pub_size = size;\n")
        parts.append(f"    g_{ident}_last_pub_valid = (uint8_t)(size <= APP_DATAFLOW_BUFFER_SIZE);\n")
        parts.append(f"    g_{ident}_last_pub_ms = g_app_elapsed_ms;\n")
        parts.append("    return efw_topic_publish(topic_id, data, size);\n}\n")
    parts.append("\n")
    for item in publisher_model:
        node = item["node"]
        ident = item["ident"]
        topic_id = item["topic_id"]
        interval_ms = item["interval_ms"]
        parts.append(f"efw_status_t app_publish_{ident}(const void *data, uint16_t size) {{\n    return efw_topic_publish({topic_id}u, data, size);\n}}\n")
        c_type = item["payload_c_type"]
        if c_type not in {"", "custom"}:
            parts.append(f"efw_status_t app_publish_{ident}_typed(const {c_type} *value) {{\n    return efw_topic_publish({topic_id}u, value, (uint16_t)sizeof({c_type}));\n}}\n")
            parts.append(f"efw_status_t app_publish_{ident}_value({c_type} value) {{\n    return app_publish_{ident}_typed(&value);\n}}\n")
        if node.get("data_expr") and node.get("size_expr"):
            parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    return app_publish_{ident}_auto_commit({topic_id}u, {node.get('data_expr')}, {node.get('size_expr')}, {interval_ms}u);\n}}\n")
        elif item["source_id"]:
            source = ctx["nodes_by_id"].get(item["source_id"])
            source_ident = c_ident(item["source_id"])
            size_expr = item["payload_size_expr"]
            if source and source.get("type") in {"sensor.custom", "sensor.line_tracking"}:
                parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    efw_status_t s;\n    s = efw_sensor_read({c_str(source['id'])}, g_{source_ident}_pub_cache.raw, (uint16_t)APP_DATAFLOW_BUFFER_SIZE);\n    if (s != EFW_OK) return s;\n    g_{source_ident}_pub_cache_size = {size_expr};\n    g_{source_ident}_pub_cache_valid = 1u;\n    return app_publish_{ident}_auto_commit({topic_id}u, g_{source_ident}_pub_cache.raw, g_{source_ident}_pub_cache_size, {interval_ms}u);\n}}\n")
            elif source and source.get("type") in {"processor.custom", "module.custom"}:
                parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    if (!g_{source_ident}_pub_cache_valid) return EFW_ERR_NOT_READY;\n    return app_publish_{ident}_auto_commit({topic_id}u, g_{source_ident}_pub_cache.raw, g_{source_ident}_pub_cache_size, {interval_ms}u);\n}}\n")
    for source_id in sorted({item["source_id"] for item in publisher_model if item["source_id"] and ctx.get("nodes_by_id", {}).get(item["source_id"], {}).get("type") == "module.custom"}):
        ident = c_ident(source_id)
        c_type = source_cache_c_type(ctx, source_id)
        parts.append(f"efw_status_t app_source_{ident}_store(const void *data, uint16_t size) {{\n    if (!data || size == 0u) return EFW_ERR_INVALID;\n    app_cache_source_{ident}(data, size);\n    return EFW_OK;\n}}\n")
        if c_type not in {"", "custom"}:
            parts.append(f"efw_status_t app_source_{ident}_store_typed(const {c_type} *value) {{\n    if (!value) return EFW_ERR_INVALID;\n    return app_source_{ident}_store(value, (uint16_t)sizeof({c_type}));\n}}\n")
            parts.append(f"efw_status_t app_source_{ident}_store_value({c_type} value) {{\n    return app_source_{ident}_store_typed(&value);\n}}\n")
    return "".join(parts)


def render_event_dispatch_fn(state_runtime):
    """Generate the dispatch callback used by efw_event_queue_process_ex."""
    parts = ["""static void app_dispatch_event_fn(const char *event_name, uint16_t topic_id,
                           const void *data, uint16_t size) {
    efw_status_t s;
    g_app_event_name = event_name;
    g_app_event_topic_id = topic_id;
    g_app_event_data = data;
    g_app_event_size = size;
    if (topic_id != 0u) {
        efw_topic_publish(topic_id, data, size);
    }
"""]
    for machine_runtime in state_runtime:
        ident = machine_runtime["ident"]
        parts.append(f"    s = app_sm_{ident}_dispatch_event(event_name, topic_id, data, size);\n")
        parts.append("    if (s == EFW_OK) return;\n")
    parts.append("}\n")
    return "".join(parts)


def render_event_queue_runtime(state_runtime):
    """Legacy wrapper: generates the dispatch fn for the events template."""
    return render_event_dispatch_fn(state_runtime)


def render_scheduler_runtime(ctx, state_runtime, publisher_model):
    parts = ["""
static efw_status_t app_update_1ms(void) {
    efw_status_t s;
    g_app_elapsed_ms += APP_PROJECT_TICK_MS;
    /* Scheduler order: generated dataflow pipelines -> line_follower flows -> tasks -> root auto-publish -> root state machines -> queued events -> module poll_all. */
    /* Dataflow pipelines are independent leaf paths discovered from graph.edges; use tasks/modules for explicit cross-pipeline ordering. */
"""]
    if dataflow_paths(ctx):
        parts.append("    /* 1. Generated runtime dataflow pipelines. */\n")
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        names = [c_ident(node_id) for node_id in path]
        fn = "app_dataflow_" + "_".join(names[:4])
        if len(names) > 4:
            fn += f"_{index}"
        period = dataflow_period_ms(ctx, path)
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = {fn}();\n        if (s != EFW_OK) return s;\n    }}\n")
    flow_tasks = {task.get("flow") for task in ctx["tasks"] if task.get("flow")}
    if ctx["flows"]:
        parts.append("    /* 2. control.line_follower flows not owned by task.periodic. */\n")
    for flow in ctx["flows"]:
        if flow["id"] in flow_tasks:
            continue
        ident = c_ident(flow["id"])
        period = int(flow.get("period_ms", ctx["project"].get("tick_ms", 1)))
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = efw_line_follower_update(&g_{ident}, 0, 0);\n        if (s != EFW_OK) return s;\n    }}\n")
    if ctx["tasks"]:
        parts.append("    /* 3. Explicit task.periodic entries. */\n")
    for task in ctx["tasks"]:
        period = int(task.get("period_ms", ctx["project"].get("tick_ms", 1)))
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        if task.get("call"):
            parts.append(f"    if ({condition}) {{\n        s = {c_ident(task['call'])}();\n        if (s != EFW_OK) return s;\n    }}\n")
        elif task.get("flow"):
            ident = c_ident(task["flow"])
            parts.append(f"    if ({condition}) {{\n        s = efw_line_follower_update(&g_{ident}, 0, 0);\n        if (s != EFW_OK) return s;\n    }}\n")
    root_publishers = [item for item in publisher_model if item["stage"] == "root app_update_1ms" and item["mode"] != "manual"]
    if root_publishers:
        parts.append("    /* 4. Root-scope auto publishers. */\n")
        for item in root_publishers:
            parts.append(f"    s = app_publish_{item['ident']}_auto();\n    if (s != EFW_OK) return s;\n")
    root_machines = [item for item in state_runtime if not item["module"]]
    if root_machines:
        parts.append("    /* 5. Root-scope state-machine ticks. */\n")
        for machine in root_machines:
            parts.append(f"    s = app_sm_{machine['ident']}_tick();\n    if (s != EFW_OK) return s;\n")
    parts.append("    /* 6. Deferred event queue dispatch. */\n")
    parts.append("    s = app_process_event_queue();\n    if (s != EFW_OK) return s;\n")
    if nodes_of(ctx, "module.custom") or nodes_of(ctx, "project.module"):
        parts.append("    /* 7. Module lifecycle poll_all. */\n")
        parts.append("    s = efw_module_poll_all();\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    return "".join(parts)


def publisher_mode(publisher: dict[str, Any]) -> str:
    if publisher.get("data_expr") and publisher.get("size_expr"):
        return "expr/size"
    if publisher.get("source"):
        return "source-auto"
    return "manual"


def publisher_stage(publisher: dict[str, Any]) -> str:
    return "module.poll" if publisher.get("module") else "root app_update_1ms"


def publisher_source_kind(ctx, publisher: dict[str, Any]) -> str | None:
    source = publisher_source_node(ctx, publisher)
    return str(source.get("type")) if source else None


def publisher_interval_ms(publisher: dict[str, Any]) -> int:
    return int(publisher.get("interval_ms", 0) or 0)


def build_publisher_runtime_model(ctx):
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


def pin_expr(pin):
    port = str(pin.get("port", "A")).upper()
    require(port in {"A", "B", "C"}, f"unsupported GPIO port: {port}")
    return f"{{ APP_GPIO_PORT_{port}, {int(pin.get('pin', 0))}u }}"


def pwm_expr(pwm):
    return f"{{ {int(pwm.get('timer', 1))}u, {int(pwm.get('channel', 1))}u }}"


def write_file(out_dir: Path, name: str, content: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_text(content.rstrip() + "\n", encoding="utf-8")


def render_text_template(template_name: str, **values: Any) -> str:
    template_path = Path(__file__).resolve().parent / "templates" / template_name
    template = Template(template_path.read_text(encoding="utf-8"))
    if "AUTO_HEADER" not in values:
        values["AUTO_HEADER"] = ""
    return template.substitute(**values)


def render_board_config(ctx):
    line_inputs = nodes_of(ctx, "hal.gpio_line_input")
    motors = nodes_of(ctx, "actuator.motor")
    board = ctx.get("board", {})
    board_profile = board.get("profile") or ctx["project"].get("board_profile") or "generic-mock"
    lines = ["""
/**
 * @file    app_board_config.h
 * @brief   Generated board constants for an EFW application graph.
 */

#ifndef APP_BOARD_CONFIG_H
#define APP_BOARD_CONFIG_H

#include <stdint.h>

typedef struct {
    uint8_t port;
    uint16_t pin;
} app_gpio_pin_t;

typedef struct {
    uint8_t timer_id;
    uint8_t channel;
} app_pwm_channel_t;

#define APP_GPIO_PORT_A 0u
#define APP_GPIO_PORT_B 1u
#define APP_GPIO_PORT_C 2u
"""]
    lines.append(f"#define APP_BOARD_PROFILE {c_str(board_profile)}\n")
    for entry in board.get("pin_plan", []):
        macro = macro_ident(f"{entry.get('node', 'node')}_{entry.get('usage', 'pin')}")
        if entry.get("timer") not in (None, "") or entry.get("channel") not in (None, ""):
            lines.append(f"#define APP_PINPLAN_{macro}_TIMER {int(entry.get('timer', 0) or 0)}u\n")
            lines.append(f"#define APP_PINPLAN_{macro}_CHANNEL {int(entry.get('channel', 0) or 0)}u\n")
        if entry.get("port") not in (None, "") and entry.get("pin") not in (None, ""):
            lines.append(f"#define APP_PINPLAN_{macro}_PORT {c_str(str(entry.get('port')).upper())}\n")
            lines.append(f"#define APP_PINPLAN_{macro}_PIN {int(entry.get('pin', 0) or 0)}u\n")
    for node in line_inputs:
        macro = macro_ident(node["id"])
        pins = ",\n    ".join(pin_expr(pin) for pin in node["pins"])
        lines.append(f"#define APP_{macro}_CHANNELS {int(node['channels'])}u\n")
        lines.append(f"static const app_gpio_pin_t APP_{macro}_PINS[APP_{macro}_CHANNELS] = {{\n    {pins},\n}};\n")
    for node in motors:
        macro = macro_ident(node["id"])
        lines.append(f"#define APP_{macro}_PWM ((app_pwm_channel_t){pwm_expr(node['pwm'])})\n")
        lines.append(f"#define APP_{macro}_DIR ((app_gpio_pin_t){pin_expr(node['dir_pin'])})\n")
    lines.append("\n#endif\n")
    return "".join(lines)


def render_topic_macros(ctx):
    lines = []
    for node in nodes_of(ctx, "event.topic"):
        lines.append(f"#define APP_TOPIC_{macro_ident(node['id'])} {int(node.get('topic_id', 0))}u")
    for index, contract in enumerate(sorted(ctx.get("contracts", {}).values(), key=lambda item: item["name"]), start=1):
        lines.append(f"#define APP_CONTRACT_{macro_ident(contract['name'])} {index}u /* c_type={contract.get('c_type', contract.get('type', 'custom'))}; size={int(contract.get('size', 0) or 0)} */")
    return "\n".join(lines)


def event_topic_id(ctx, topic_ref):
    topic = ctx["nodes_by_id"].get(topic_ref)
    return int(topic.get("topic_id", 0)) if topic else 0


def manifest_template_values(ctx):
    return {
        "APP_USE_HAL": c_bool(len(nodes_of(ctx, 'hal.gpio_line_input') + nodes_of(ctx, 'hal.custom'))),
        "APP_USE_SENSOR": c_bool(len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom'))),
        "APP_USE_LINE_TRACKING": c_bool(len(nodes_of(ctx, 'sensor.line_tracking'))),
        "APP_USE_ACTUATOR": c_bool(len(nodes_of(ctx, 'actuator.motor') + nodes_of(ctx, 'actuator.custom'))),
        "APP_USE_MOTOR": c_bool(len(nodes_of(ctx, 'actuator.motor'))),
        "APP_USE_ALGORITHM": c_bool(len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom'))),
        "APP_USE_PID": c_bool(len(nodes_of(ctx, 'algorithm.pid'))),
        "APP_USE_PROCESSOR": c_bool(len(nodes_of(ctx, 'processor.custom'))),
        "APP_USE_MODULE": c_bool(len(nodes_of(ctx, 'module.custom') + nodes_of(ctx, 'project.module'))),
        "APP_USE_EVENT": c_bool(len(nodes_of(ctx, 'event.topic') + nodes_of(ctx, 'event.publisher') + nodes_of(ctx, 'event.subscriber'))),
        "APP_USE_STATE_MACHINE": c_bool(len(nodes_of(ctx, 'state.machine') + nodes_of(ctx, 'state.state') + nodes_of(ctx, 'state.transition'))),
        "APP_PROJECT_TICK_MS": f"{int(ctx['project'].get('tick_ms', 1))}u",
        "APP_HAL_COUNT": len(nodes_of(ctx, 'hal.gpio_line_input') + nodes_of(ctx, 'hal.custom')),
        "APP_SENSOR_COUNT": len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom')),
        "APP_ACTUATOR_COUNT": len(nodes_of(ctx, 'actuator.motor') + nodes_of(ctx, 'actuator.custom')),
        "APP_ALGO_COUNT": len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom')),
        "APP_PROCESSOR_COUNT": len(nodes_of(ctx, 'processor.custom')),
        "APP_DATAFLOW_PIPELINE_COUNT": len(dataflow_paths(ctx)),
        "APP_DATAFLOW_BUFFER_SIZE": f"{dataflow_buffer_size(ctx)}u",
        "APP_MODULE_COUNT": len(nodes_of(ctx, 'module.custom') + nodes_of(ctx, 'project.module')),
        "APP_TOPIC_COUNT": len(nodes_of(ctx, 'event.topic')),
        "APP_CONTRACT_COUNT": len(ctx.get('contracts', {})),
        "APP_STATE_COUNT": len(nodes_of(ctx, 'state.state')),
        "TOPIC_MACROS": render_topic_macros(ctx),
    }


def render_manifest(ctx):
    return render_text_template("app_manifest.h.tpl", **manifest_template_values(ctx))


def render_components_h():
    return """
/**
 * @file    app_components.h
 * @brief   Generated algorithm/module registration entry point.
 */

#ifndef APP_COMPONENTS_H
#define APP_COMPONENTS_H

#include "efw/efw.h"

efw_status_t app_components_register(void);

#endif
"""


def components_template_values(ctx):
    module_runtime_model = build_project_module_runtime_model(ctx)
    algo_defs = render_algorithm_runtime_defs(ctx)
    custom_module_defs = render_custom_module_runtime_defs(ctx)
    project_module_defs = render_project_module_shells(module_runtime_model)
    algo_regs = "".join(
        f"    s = efw_algo_register(&g_{c_ident(node['id'])}_algo);\n    if (s != EFW_OK) return s;\n"
        for node in nodes_of(ctx, "algorithm.pid") + nodes_of(ctx, "algorithm.custom")
    )
    custom_module_regs = "".join(
        f"    s = efw_module_register(&g_{c_ident(node['id'])}_module);\n    if (s != EFW_OK) return s;\n"
        for node in nodes_of(ctx, "module.custom")
    )
    project_module_regs = render_project_module_registrations(module_runtime_model)
    return {
        "ALGORITHM_RUNTIME_DEFS": algo_defs,
        "CUSTOM_MODULE_RUNTIME_DEFS": custom_module_defs,
        "PROJECT_MODULE_RUNTIME_DEFS": project_module_defs,
        "ALGORITHM_REGISTRATIONS": algo_regs,
        "CUSTOM_MODULE_REGISTRATIONS": custom_module_regs,
        "PROJECT_MODULE_REGISTRATIONS": project_module_regs,
    }


def render_algorithm_runtime_defs(ctx):
    parts = []
    for node in nodes_of(ctx, "algorithm.pid"):
        ident = c_ident(node["id"])
        parts.append(f"""static efw_pid_t g_{ident}_ctx = {{
    .kp = {c_float(node.get('kp', 18.0))},
    .ki = {c_float(node.get('ki', 0.0))},
    .kd = {c_float(node.get('kd', 2.5))},
    .kff = {c_float(node.get('kff', 0.0))},
    .integral_min = {c_float(node.get('integral_min', -20.0))},
    .integral_max = {c_float(node.get('integral_max', 20.0))},
    .out_min = {c_float(node.get('out_min', -60.0))},
    .out_max = {c_float(node.get('out_max', 60.0))},
    .anti_windup = {c_bool(node.get('anti_windup', True))},
}};

static efw_algo_ops_t g_{ident}_algo = {{
    .name = {c_str(node['id'])},
    .type = EFW_ALGO_CONTROL,
    .ctx = &g_{ident}_ctx,
    .run = efw_pid_run,
}};

""")
    for node in nodes_of(ctx, "algorithm.custom"):
        ident = c_ident(node["id"])
        run = c_ident(node["run"])
        ctx_symbol = node.get("ctx", "0")
        algo_type = node.get("algo_type", "EFW_ALGO_CUSTOM")
        parts.append(f"extern efw_status_t {run}(void *ctx, const void *in, void *out);\n")
        parts.append(f"""static efw_algo_ops_t g_{ident}_algo = {{
    .name = {c_str(node['id'])},
    .type = {algo_type},
    .ctx = {ctx_symbol},
    .run = {run},
}};

""")
    return "".join(parts)


def render_custom_module_runtime_defs(ctx):
    parts = []
    for node in nodes_of(ctx, "module.custom"):
        ident = c_ident(node["id"])
        module_type = node.get("module_type", "EFW_MODULE_CUSTOM")
        callbacks = {}
        for cb in ["init", "start", "stop", "poll"]:
            name = node.get(cb)
            callbacks[cb] = c_ident(name) if name else "0"
            if name:
                parts.append(f"extern efw_status_t {c_ident(name)}(void *ctx);\n")
        parts.append(f"""static efw_module_ops_t g_{ident}_module = {{
    .name = {c_str(node['id'])},
    .type = {module_type},
    .ctx = {node.get('ctx', '0')},
    .init = {callbacks['init']},
    .start = {callbacks['start']},
    .stop = {callbacks['stop']},
    .poll = {callbacks['poll']},
}};

""")
    return "".join(parts)


def render_components_c(ctx):
    return render_text_template("app_components.c.tpl", **components_template_values(ctx))


def render_platform_h():
    return """
/**
 * @file    app_platform.h
 * @brief   Generated platform registration interface.
 */

#ifndef APP_PLATFORM_H
#define APP_PLATFORM_H

#include <stdint.h>
#include "efw/efw.h"
#include "app_board_config.h"

efw_status_t app_platform_register(void);
void app_platform_set_line_state(const char *input_name, const uint16_t *values, uint8_t count);

#endif
"""


def hal_type_expr(node):
    mapping = {
        "gpio": "EFW_HAL_GPIO",
        "i2c": "EFW_HAL_I2C",
        "spi": "EFW_HAL_SPI",
        "uart": "EFW_HAL_UART",
        "timer": "EFW_HAL_TIMER",
        "pwm": "EFW_HAL_PWM",
        "adc": "EFW_HAL_ADC",
        "custom": "EFW_HAL_CUSTOM",
    }
    return mapping.get(str(node.get("hal_type", "custom")), str(node.get("hal_type", "EFW_HAL_CUSTOM")))


def actuator_type_expr(node):
    mapping = {
        "motor": "EFW_ACTUATOR_MOTOR",
        "servo": "EFW_ACTUATOR_SERVO",
        "relay": "EFW_ACTUATOR_RELAY",
        "led": "EFW_ACTUATOR_LED",
        "custom": "EFW_ACTUATOR_CUSTOM",
    }
    return mapping.get(str(node.get("actuator_type", "custom")), str(node.get("actuator_type", "EFW_ACTUATOR_CUSTOM")))


def sensor_type_expr(node):
    mapping = {
        "line_tracking": "EFW_SENSOR_LINE_TRACKING",
        "imu": "EFW_SENSOR_IMU",
        "encoder": "EFW_SENSOR_ENCODER",
        "ultrasonic": "EFW_SENSOR_ULTRASONIC",
        "custom": "EFW_SENSOR_CUSTOM",
    }
    return mapping.get(str(node.get("sensor_type", "custom")), str(node.get("sensor_type", "EFW_SENSOR_CUSTOM")))


def build_hal_runtime_model(ctx):
    model = []
    for node in nodes_of(ctx, "hal.gpio_line_input"):
        model.append({"node": node, "kind": "line_input", "ident": c_ident(node["id"]), "macro": macro_ident(node["id"])})
    for node in nodes_of(ctx, "hal.custom"):
        model.append({"node": node, "kind": "custom_hal", "ident": c_ident(node["id"])})
    return model


def build_sensor_runtime_model(ctx):
    model = []
    for node in nodes_of(ctx, "sensor.line_tracking"):
        model.append({"node": node, "kind": "line_sensor", "ident": c_ident(node["id"]), "input_node": ctx["nodes_by_id"][node["input"]]})
    for node in nodes_of(ctx, "sensor.custom"):
        model.append({"node": node, "kind": "custom_sensor", "ident": c_ident(node["id"])})
    return model


def build_actuator_runtime_model(ctx):
    model = []
    for node in nodes_of(ctx, "actuator.motor"):
        model.append({"node": node, "kind": "motor", "ident": c_ident(node["id"]), "macro": macro_ident(node["id"])})
    for node in nodes_of(ctx, "actuator.custom"):
        model.append({"node": node, "kind": "custom_actuator", "ident": c_ident(node["id"])})
    return model


def render_platform_type_helpers(line_inputs, line_sensors, motors):
    parts = []
    if line_inputs:
        parts.append("""typedef struct {
    uint16_t channel[EFW_LINE_TRACKING_MAX_CHANNELS];
    uint8_t channel_count;
    const app_gpio_pin_t *pins;
} app_line_input_ctx_t;

static uint8_t app_name_eq(const char *a, const char *b) {
    if (!a || !b) return 0u;
    while (*a && *b) {
        if (*a != *b) return 0u;
        ++a;
        ++b;
    }
    return (*a == *b) ? 1u : 0u;
}

static efw_status_t line_input_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    app_line_input_ctx_t *input = (app_line_input_ctx_t *)ctx;
    efw_line_tracking_data_t *out = (efw_line_tracking_data_t *)buf;
    if (!input || !out || len < sizeof(efw_line_tracking_data_t)) return EFW_ERR_INVALID;

    /* Hardware implementation:
     * Read GPIO pins for each channel and store in out->value[]
     *
     * Example for STM32 HAL:
     *   for (uint8_t i = 0; i < input->channel_count; ++i) {
     *       GPIO_PinState state = HAL_GPIO_ReadPin(input->pins[i].port, 1 << input->pins[i].pin);
     *       out->value[i] = (state == GPIO_PIN_SET) ? 1 : 0;
     *   }
     *
     * Example for ESP-IDF:
     *   for (uint8_t i = 0; i < input->channel_count; ++i) {
     *       out->value[i] = gpio_get_level(input->pins[i].pin);
     *   }
     *
     * Example for analog sensors (ADC):
     *   for (uint8_t i = 0; i < input->channel_count; ++i) {
     *       out->value[i] = (uint16_t)adc_read(input->pins[i].pin);
     *   }
     */

    /* TODO: Replace with real hardware calls */
    out->count = input->channel_count;
    for (uint8_t i = 0; i < input->channel_count; ++i) {
        out->value[i] = input->channel[i];
    }
    if (actual) *actual = sizeof(efw_line_tracking_data_t);
    return EFW_OK;
}

""")
    if line_sensors:
        parts.append("""static efw_status_t line_sensor_read(void *ctx, void *out) {
    return efw_hal_read((const char *)ctx, out, sizeof(efw_line_tracking_data_t), 0);
}

""")
    if motors:
        parts.append("""typedef struct {
    app_pwm_channel_t pwm;
    app_gpio_pin_t dir_pin;
    float last_speed;
    float last_direction;
} app_motor_ctx_t;

static efw_status_t motor_write(void *ctx, const void *cmd) {
    app_motor_ctx_t *motor = (app_motor_ctx_t *)ctx;
    const efw_motor_cmd_t *motor_cmd = (const efw_motor_cmd_t *)cmd;
    if (!motor || !motor_cmd) return EFW_ERR_INVALID;

    /* Hardware implementation:
     * 1. Set direction GPIO based on motor_cmd->direction
     *    - direction > 0: forward (set dir_pin HIGH)
     *    - direction < 0: reverse (set dir_pin LOW)
     *    - direction == 0: stop
     *
     * 2. Set PWM duty cycle based on motor_cmd->speed
     *    - speed range: [min_speed, max_speed]
     *    - Convert to PWM duty: duty = |speed| / max_speed * 100%
     *
     * Example for STM32 HAL:
     *   HAL_GPIO_WritePin(motor->dir_pin.port, 1 << motor->dir_pin.pin,
     *                     motor_cmd->direction > 0 ? GPIO_PIN_SET : GPIO_PIN_RESET);
     *   __HAL_TIM_SET_COMPARE(&htim[motor->pwm.timer_id], motor->pwm.channel,
     *                         (uint32_t)(fabsf(motor_cmd->speed) * htim[motor->pwm.timer_id].Init.Period));
     *
     * Example for ESP-IDF:
     *   gpio_set_level(motor->dir_pin.pin, motor_cmd->direction > 0 ? 1 : 0);
     *   ledc_set_duty(LEDC_HIGH_SPEED_MODE, motor->pwm.channel,
     *                 (uint32_t)(fabsf(motor_cmd->speed) / 100.0f * 8191));
     *   ledc_update_duty(LEDC_HIGH_SPEED_MODE, motor->pwm.channel);
     */

    /* TODO: Replace with real hardware calls */
    motor->last_speed = motor_cmd->speed;
    motor->last_direction = motor_cmd->direction;
    return EFW_OK;
}

""")
    return "".join(parts)


def render_platform_externs(ctx):
    parts = []
    for node in nodes_of(ctx, "hal.custom"):
        for cb, sig in [("init", "void *ctx"), ("read", "void *ctx, void *buf, uint16_t len, uint16_t *actual"), ("write", "void *ctx, const void *buf, uint16_t len, uint16_t *actual"), ("ioctl", "void *ctx, uint32_t cmd, void *arg")]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}({sig});\n")
    for node in nodes_of(ctx, "actuator.custom"):
        parts.append(f"extern efw_status_t {c_ident(node['write'])}(void *ctx, const void *cmd);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
        if node.get("enable"):
            parts.append(f"extern efw_status_t {c_ident(node['enable'])}(void *ctx);\n")
        if node.get("disable"):
            parts.append(f"extern efw_status_t {c_ident(node['disable'])}(void *ctx);\n")
    for node in nodes_of(ctx, "sensor.custom"):
        parts.append(f"extern efw_status_t {c_ident(node['read'])}(void *ctx, void *out);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
    return "".join(parts)


def render_hal_runtime_defs(hal_runtime_model):
    parts = []
    for item in hal_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "line_input":
            macro = item["macro"]
            parts.append(f"""static app_line_input_ctx_t g_{ident}_ctx = {{
    .channel_count = APP_{macro}_CHANNELS,
    .pins = APP_{macro}_PINS,
}};

static efw_hal_ops_t g_{ident}_hal = {{
    .name = {c_str(node['id'])},
    .type = EFW_HAL_GPIO,
    .bus_id = {int(node.get('bus_id', 0))},
    .ctx = &g_{ident}_ctx,
    .read = line_input_read,
}};

""")
        else:
            parts.append(f"""static efw_hal_ops_t g_{ident}_hal = {{
    .name = {c_str(node['id'])},
    .type = {hal_type_expr(node)},
    .bus_id = {int(node.get('bus_id', 0))},
    .ctx = {node.get('ctx', '0')},
    .init = {c_ident(node['init']) if node.get('init') else '0'},
    .read = {c_ident(node['read']) if node.get('read') else '0'},
    .write = {c_ident(node['write']) if node.get('write') else '0'},
    .ioctl = {c_ident(node['ioctl']) if node.get('ioctl') else '0'},
}};

""")
    return "".join(parts)


def render_sensor_runtime_defs(sensor_runtime_model):
    parts = []
    for item in sensor_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "line_sensor":
            input_node = item["input_node"]
            parts.append(f"""static efw_sensor_ops_t g_{ident}_sensor = {{
    .name = {c_str(node['id'])},
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = {int(input_node['channels'])}u,
    .hal_name = {c_str(node['input'])},
    .ctx = (void *){c_str(node['input'])},
    .read = line_sensor_read,
}};

""")
        else:
            parts.append(f"""static efw_sensor_ops_t g_{ident}_sensor = {{
    .name = {c_str(node['id'])},
    .type = {sensor_type_expr(node)},
    .channel_count = {int(node.get('channel_count', 1))}u,
    .hal_name = {c_str(node.get('hal_name'))},
    .comm_name = {c_str(node.get('comm_name'))},
    .ctx = {node.get('ctx', '0')},
    .init = {c_ident(node['init']) if node.get('init') else '0'},
    .read = {c_ident(node['read'])},
}};

""")
    return "".join(parts)


def render_actuator_runtime_defs(actuator_runtime_model):
    parts = []
    for item in actuator_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "motor":
            macro = item["macro"]
            parts.append(f"""static app_motor_ctx_t g_{ident}_ctx = {{
    .pwm = APP_{macro}_PWM,
    .dir_pin = APP_{macro}_DIR,
}};

static efw_actuator_ops_t g_{ident}_motor = {{
    .name = {c_str(node['id'])},
    .type = EFW_ACTUATOR_MOTOR,
    .ctx = &g_{ident}_ctx,
    .write = motor_write,
}};

""")
        else:
            parts.append(f"""static efw_actuator_ops_t g_{ident}_actuator = {{
    .name = {c_str(node['id'])},
    .type = {actuator_type_expr(node)},
    .hal_name = {c_str(node.get('hal_name'))},
    .comm_name = {c_str(node.get('comm_name'))},
    .ctx = {node.get('ctx', '0')},
    .init = {c_ident(node['init']) if node.get('init') else '0'},
    .enable = {c_ident(node['enable']) if node.get('enable') else '0'},
    .disable = {c_ident(node['disable']) if node.get('disable') else '0'},
    .write = {c_ident(node['write'])},
}};

""")
    return "".join(parts)


def render_platform_registrations(hal_runtime_model, sensor_runtime_model, actuator_runtime_model):
    parts = ["efw_status_t app_platform_register(void) {\n    efw_status_t s;\n"]
    for item in hal_runtime_model:
        parts.append(f"    s = efw_hal_register(&g_{item['ident']}_hal);\n    if (s != EFW_OK) return s;\n")
    for item in sensor_runtime_model:
        parts.append(f"    s = efw_sensor_register(&g_{item['ident']}_sensor);\n    if (s != EFW_OK) return s;\n")
    for item in actuator_runtime_model:
        suffix = 'motor' if item['kind'] == 'motor' else 'actuator'
        parts.append(f"    s = efw_actuator_register(&g_{item['ident']}_{suffix});\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    return "".join(parts)


def platform_template_values(ctx):
    line_inputs = nodes_of(ctx, "hal.gpio_line_input")
    line_sensors = nodes_of(ctx, "sensor.line_tracking")
    motors = nodes_of(ctx, "actuator.motor")
    hal_runtime_model = build_hal_runtime_model(ctx)
    sensor_runtime_model = build_sensor_runtime_model(ctx)
    actuator_runtime_model = build_actuator_runtime_model(ctx)
    line_state_body = []
    if not line_inputs:
        line_state_body.append("    (void)count;\n")
    for node in line_inputs:
        ident = c_ident(node["id"])
        line_state_body.append(f"    if (app_name_eq(input_name, {c_str(node['id'])})) {{\n        uint8_t n = (count < g_{ident}_ctx.channel_count) ? count : g_{ident}_ctx.channel_count;\n        for (uint8_t i = 0; i < n; ++i) g_{ident}_ctx.channel[i] = values[i];\n        return;\n    }}\n")
    return {
        "TYPE_HELPERS": render_platform_type_helpers(line_inputs, line_sensors, motors),
        "EXTERNS": render_platform_externs(ctx),
        "HAL_DEFS": render_hal_runtime_defs(hal_runtime_model),
        "SENSOR_DEFS": render_sensor_runtime_defs(sensor_runtime_model),
        "ACTUATOR_DEFS": render_actuator_runtime_defs(actuator_runtime_model),
        "REGISTRATIONS": render_platform_registrations(hal_runtime_model, sensor_runtime_model, actuator_runtime_model),
        "LINE_STATE_BODY": "".join(line_state_body),
    }


def render_platform_c(ctx):
    return render_text_template("app_platform.c.tpl", **platform_template_values(ctx))


def render_bootstrap_h(ctx):
    state_runtime_model = build_state_runtime_model(ctx)
    lines = ["""
/**
 * @file    app_bootstrap.h
 * @brief   Generated app init and 1 ms loop entry points.
 */

#ifndef APP_BOOTSTRAP_H
#define APP_BOOTSTRAP_H

#include "efw/efw.h"

efw_status_t app_init(void);
efw_status_t app_loop_tick(void);
efw_status_t app_loop_1ms(void);
efw_status_t app_post_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);
efw_status_t app_process_event_queue(void);
efw_status_t app_poll_forever(void);
efw_status_t app_main(void);
const char *app_current_event_name(void);
uint16_t app_current_event_topic_id(void);
const void *app_current_event_data(void);
uint16_t app_current_event_size(void);

"""]
    for node in nodes_of(ctx, "event.publisher"):
        ident = c_ident(node["id"])
        lines.append(f"efw_status_t app_publish_{ident}(const void *data, uint16_t size);\n")
        c_type = publisher_payload_c_type(ctx, node)
        if c_type not in {"", "custom"}:
            lines.append(f"efw_status_t app_publish_{ident}_typed(const {c_type} *value);\n")
            lines.append(f"efw_status_t app_publish_{ident}_value({c_type} value);\n")
        if node.get("data_expr") and node.get("size_expr"):
            lines.append(f"efw_status_t app_publish_{ident}_auto(void);\n")
    if nodes_of(ctx, "event.publisher"):
        lines.append("\n")
    for source_id in sorted({str(node.get("source")) for node in nodes_of(ctx, "event.publisher") if node.get("source") and ctx.get("nodes_by_id", {}).get(node.get("source"), {}).get("type") == "module.custom"}):
        ident = c_ident(source_id)
        c_type = source_cache_c_type(ctx, source_id)
        lines.append(f"efw_status_t app_source_{ident}_store(const void *data, uint16_t size);\n")
        if c_type not in {"", "custom"}:
            lines.append(f"efw_status_t app_source_{ident}_store_typed(const {c_type} *value);\n")
            lines.append(f"efw_status_t app_source_{ident}_store_value({c_type} value);\n")
    if nodes_of(ctx, "event.publisher"):
        lines.append("\n")
    lines.append(render_state_api_declarations(state_runtime_model))
    lines.append("\n#endif\n")
    return "".join(lines)

def render_state_helpers(ctx):
    """Generate helper functions needed by state machines and processors."""
    parts = []
    state_runtime = build_state_runtime_model(ctx)
    has_processors = bool(nodes_of(ctx, "processor.custom"))
    if state_runtime or has_processors:
        parts.append("static efw_status_t app_noop_status(void *ctx) { EFW_UNUSED(ctx); return EFW_OK; }\n")
        parts.append("static uint8_t app_bootstrap_name_eq(const char *a, const char *b) { if (!a || !b) return 0u; while (*a && *b) { if (*a != *b) return 0u; ++a; ++b; } return (*a == *b) ? 1u : 0u; }\n")
    if state_runtime:
        parts.append("static uint8_t app_bootstrap_event_matches(const char *trigger, const char *event_name, uint16_t topic_id) {\n")
        parts.append("    if (trigger && event_name && trigger[0] == 'e' && trigger[1] == 'v' && trigger[2] == 'e' && trigger[3] == 'n' && trigger[4] == 't' && trigger[5] == ':' && app_bootstrap_name_eq(trigger + 6, event_name)) return 1u;\n")
        for topic in nodes_of(ctx, "event.topic"):
            parts.append(f"    if (topic_id == {event_topic_id(ctx, topic['id'])}u && app_bootstrap_name_eq(trigger, {c_str(publisher_event_trigger_match(topic['id']))})) return 1u;\n")
        parts.append("    return 0u;\n}\n")
    return "".join(parts)

def render_state_logic_blocks(ctx):
    parts = []
    state_runtime = build_state_runtime_model(ctx)
    for node in nodes_of(ctx, "state.state"):
        for cb, sig in [("on_enter", "void *ctx"), ("on_update", "void *ctx"), ("on_exit", "void *ctx")]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}({sig});\n")
    for node in nodes_of(ctx, "state.transition"):
        if node.get("condition"):
            parts.append(f"extern int {c_ident(node['condition'])}(void);\n")
        if node.get("action"):
            parts.append(f"extern efw_status_t {c_ident(node['action'])}(void);\n")
    if parts:
        parts.append("\n")
    for machine_runtime in state_runtime:
        parts.append(render_state_machine_bundle(machine_runtime))
    for node in nodes_of(ctx, "processor.custom"):
        if node.get("process"):
            process = c_ident(node["process"])
            ident = c_ident(node["id"])
            input_contract = str(node.get("input_contract", "custom")).replace("*/", "* /")
            output_contract = str(node.get("output_contract", "custom")).replace("*/", "* /")
            parts.append(f"extern efw_status_t {process}(void *ctx, const void *in, void *out);\n")
            parts.append(f"static efw_status_t app_processor_{ident}(const void *in, void *out) {{\n")
            parts.append(f"    /* input_contract={input_contract}; output_contract={output_contract} */\n")
            parts.append(f"    return {process}({node.get('ctx', '0')}, in, out);\n")
            parts.append("}\n\n")
    return "".join(parts)

def render_dataflow_pipelines(ctx):
    parts = []
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        names = [c_ident(node_id) for node_id in path]
        fn = "app_dataflow_" + "_".join(names[:4])
        if len(names) > 4:
            fn += f"_{index}"
        parts.append(f"static efw_status_t {fn}(void) {{\n")
        parts.append("    efw_status_t s;\n")
        parts.append("    app_dataflow_buffer_t buf_a;\n")
        parts.append("    app_dataflow_buffer_t buf_b;\n")
        current = "buf_a.raw"
        scratch = "buf_b.raw"
        first = ctx["nodes_by_id"][path[0]]
        parts.append(f"    s = efw_sensor_read({c_str(first['id'])}, {current}, (uint16_t)APP_DATAFLOW_BUFFER_SIZE);\n")
        parts.append("    if (s != EFW_OK) return s;\n")
        if source_auto_publishers(ctx, first["id"]):
            parts.append(f"    app_cache_source_{c_ident(first['id'])}({current}, {publisher_payload_size_expr(ctx, source_auto_publishers(ctx, first['id'])[0])});\n")
        for node_id in path[1:]:
            node = ctx["nodes_by_id"][node_id]
            node_type = node.get("type")
            if node_type == "processor.custom":
                parts.append(f"    s = app_processor_{c_ident(node['id'])}({current}, {scratch});\n")
                parts.append("    if (s != EFW_OK) return s;\n")
                if source_auto_publishers(ctx, node["id"]):
                    parts.append(f"    app_cache_source_{c_ident(node['id'])}({scratch}, {publisher_payload_size_expr(ctx, source_auto_publishers(ctx, node['id'])[0])});\n")
                current, scratch = scratch, current
            elif node_type in {"algorithm.pid", "algorithm.custom"}:
                parts.append(f"    s = efw_algo_run({c_str(node['id'])}, {current}, (uint16_t)sizeof(efw_pid_input_t), {scratch}, (uint16_t)sizeof(efw_pid_output_t));\n")
                parts.append("    if (s != EFW_OK) return s;\n")
                current, scratch = scratch, current
            elif node_type in {"actuator.motor", "actuator.custom"}:
                parts.append(f"    s = efw_actuator_write({c_str(node['id'])}, {current}, (uint16_t)sizeof(efw_motor_cmd_t));\n")
                parts.append("    if (s != EFW_OK) return s;\n")
        parts.append("    return EFW_OK;\n")
        parts.append("}\n\n")
    return "".join(parts)


def render_contract_size_checks(ctx):
    lines = ["/* Built-in contract ABI checks: keep metadata sizes synchronized with EFW C structs. */"]
    for name in sorted(ctx.get("contracts", {})):
        if name not in BUILTIN_CONTRACTS:
            continue
        contract = ctx["contracts"][name]
        c_type = str(contract.get("c_type") or BUILTIN_CONTRACTS[name].get("c_type") or name)
        size = int(contract.get("size", 0) or 0)
        if size <= 0:
            continue
        ident = macro_ident(name).lower()
        lines.append(f"typedef char app_contract_size_check_{ident}[(sizeof({c_type}) == {size}u) ? 1 : -1];")
    return "\n".join(lines) + "\n\n"


def bootstrap_template_values(ctx):
    publisher_model = build_publisher_runtime_model(ctx)
    state_runtime = build_state_runtime_model(ctx)
    line_follower_defs = []
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        weights = ", ".join(c_float(value) for value in flow["weights"])
        line_follower_defs.append(f"static efw_line_follower_t g_{ident};\n")
        line_follower_defs.append(f"static const float g_{ident}_weights[] = {{ {weights} }};\n")
    subscriber_externs = []
    for task in ctx["tasks"]:
        if task.get("call"):
            subscriber_externs.append(f"extern efw_status_t {c_ident(task['call'])}(void);\n")
    for node in nodes_of(ctx, "event.subscriber"):
        subscriber_externs.append(f"extern void {c_ident(node['callback'])}(uint16_t topic_id, const void *data, uint16_t size, void *user);\n")
    bind_lines = ["static efw_status_t app_bind_handles(void) {\n    efw_status_t s;\n"]
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        bind_lines.append(f"""    const efw_line_follower_config_t {ident}_config = {{
        .sensor_name = {c_str(flow['sensor'])},
        .pid_name = {c_str(flow['pid'])},
        .left_motor = {c_str(flow['left_motor'])},
        .right_motor = {c_str(flow['right_motor'])},
        .weights = g_{ident}_weights,
        .base_speed = {c_float(flow.get('base_speed', 65.0))},
        .min_speed = {c_float(flow.get('min_speed', 0.0))},
        .max_speed = {c_float(flow.get('max_speed', 100.0))},
        .dt = {c_float(flow.get('dt', 0.001))},
        .active_value = {int(flow.get('active_value', 1))}u,
        .binary_mode = {c_bool(flow.get('binary_mode', True))},
    }};
    s = efw_line_follower_bind_config(&g_{ident}, &{ident}_config);
    if (s != EFW_OK) return s;
""")
    for node in nodes_of(ctx, "event.subscriber"):
        bind_lines.append(f"    s = efw_topic_subscribe({event_topic_id(ctx, node['topic'])}u, {c_ident(node['callback'])}, {node.get('user', '0')});\n    if (s != EFW_OK) return s;\n")
    for machine_runtime in state_runtime:
        bind_lines.append(f"    s = app_{machine_runtime['ident']}_register();\n    if (s != EFW_OK) return s;\n")
    bind_lines.append("    return EFW_OK;\n}\n\n")
    return {
        "CONTRACT_SIZE_CHECKS": render_contract_size_checks(ctx),
        "STATE_HELPERS": render_state_helpers(ctx),
        "STATE_LOGIC_BLOCKS": render_state_logic_blocks(ctx),
        "DATAFLOW_PIPELINES": render_dataflow_pipelines(ctx),
        "LINE_FOLLOWER_DEFS": "".join(line_follower_defs),
        "PUBLISHER_RUNTIME": render_publisher_runtime(ctx, publisher_model),
        "EXTERNS": "".join(subscriber_externs),
        "BIND_HANDLES": "".join(bind_lines),
        "SCHEDULER_RUNTIME": render_scheduler_runtime(ctx, state_runtime, publisher_model),
        "EVENT_DISPATCH_FN": render_event_dispatch_fn(state_runtime),
    }


def render_bootstrap_c(ctx):
    return render_text_template("app_bootstrap.c.tpl", **bootstrap_template_values(ctx))


def render_publishers_c(ctx):
    values = bootstrap_template_values(ctx)
    return render_text_template("app_publishers.c.tpl", **values)


def render_events_c(ctx):
    values = bootstrap_template_values(ctx)
    return render_text_template("app_events.c.tpl", **values)


def render_state_machines_c(ctx):
    values = bootstrap_template_values(ctx)
    return render_text_template("app_state_machines.c.tpl", **values)


def first_line_input(ctx):
    line_inputs = nodes_of(ctx, "hal.gpio_line_input")
    return line_inputs[0] if line_inputs else None


def main_template_values(ctx):
    line_input = first_line_input(ctx)
    if line_input:
        channels = int(line_input["channels"])
        centered = ["0"] * channels
        centered[channels // 2] = "1"
        setup = f"    const uint16_t centered_line[{channels}] = {{ {', '.join(centered)} }};\n    app_platform_set_line_state({c_str(line_input['id'])}, centered_line, {channels}u);\n"
    else:
        setup = ""
    return {"SETUP": setup}


def render_main_c(ctx):
    return render_text_template("main.c.tpl", **main_template_values(ctx))


def render_cmake(ctx):
    target = c_ident(ctx["project"].get("name", "generated_app"))
    custom_c_files = [item["path"] for item in ctx["custom_files"] + ctx["board_adapters"] if item["path"].endswith(".c")]
    custom_sources = "".join(f"    {path}\n" for path in custom_c_files)
    # Add split source files if they exist
    state_runtime = build_state_runtime_model(ctx)
    publisher_model = build_publisher_runtime_model(ctx)
    extra_sources = []
    if publisher_model or ctx.get("flows") or dataflow_paths(ctx):
        extra_sources.append("app_publishers.c")
    if nodes_of(ctx, "event.topic") or nodes_of(ctx, "event.publisher"):
        extra_sources.append("app_events.c")
    if state_runtime or nodes_of(ctx, "processor.custom"):
        extra_sources.append("app_state_machines.c")
    extra = "".join(f"    {src}\n" for src in extra_sources)
    return f"""
# Optional generated-app CMake snippet.
add_executable(efw_app_{target}
    main.c
    app_bootstrap.c
    app_components.c
    app_platform.c
{extra}{custom_sources})
target_include_directories(efw_app_{target} PRIVATE ${{CMAKE_CURRENT_LIST_DIR}})
target_link_libraries(efw_app_{target} PRIVATE efw)
"""


def render_application_files(ctx):
    files = {
        "app_board_config.h": render_board_config(ctx),
        "app_manifest.h": render_manifest(ctx),
        "app_components.h": render_components_h(),
        "app_components.c": render_components_c(ctx),
        "app_platform.h": render_platform_h(),
        "app_platform.c": render_platform_c(ctx),
        "app_bootstrap.h": render_bootstrap_h(ctx),
        "app_bootstrap.c": render_bootstrap_c(ctx),
        "main.c": render_main_c(ctx),
        "CMakeLists.generated.txt": render_cmake(ctx),
    }
    # Add split files if they have content
    state_runtime = build_state_runtime_model(ctx)
    publisher_model = build_publisher_runtime_model(ctx)
    has_publishers = bool(publisher_model or ctx.get("flows") or dataflow_paths(ctx))
    has_events = bool(nodes_of(ctx, "event.topic") or nodes_of(ctx, "event.publisher"))
    has_state_content = bool(state_runtime or nodes_of(ctx, "processor.custom"))
    if has_publishers:
        files["app_publishers.c"] = render_publishers_c(ctx)
    if has_events:
        files["app_events.c"] = render_events_c(ctx)
    if has_state_content:
        files["app_state_machines.c"] = render_state_machines_c(ctx)
    for item in ctx["custom_files"] + ctx["board_adapters"]:
        files[item["path"]] = item["content"]
    return files


def preview_application_files(graph_path: Path, out_dir: Path):
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = validate_graph(graph)
    files = render_application_files(ctx)
    preview = []
    for rel_path, content in sorted(files.items()):
        target = out_dir / rel_path
        new_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        item = {"path": rel_path, "new_sha": new_sha, "new_lines": content.count("\n") + 1}
        if not target.exists():
            item["status"] = "create"
        else:
            old_content = target.read_text(encoding="utf-8")
            item["old_sha"] = hashlib.sha256(old_content.encode("utf-8")).hexdigest()[:12]
            item["old_lines"] = old_content.count("\n") + 1
            if old_content == content:
                item["status"] = "same"
            else:
                item["status"] = "backup+overwrite"
                item["protected_by"] = ".efw_backup"
        preview.append(item)
    if out_dir.exists():
        generated_set = set(files)
        for target in sorted(path for path in out_dir.rglob("*") if path.is_file()):
            rel = target.relative_to(out_dir).as_posix()
            if rel not in generated_set and not rel.startswith(".efw_backup/"):
                preview.append({"path": rel, "status": "preserve", "old_lines": target.read_text(encoding="utf-8", errors="ignore").count("\n") + 1, "protected_by": "user-file-preserve"})
    return preview


def generate(graph_path: Path, out_dir: Path, force: bool) -> None:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = validate_graph(graph, print_warnings=True)
    if out_dir.exists() and any(out_dir.iterdir()):
        require(force, f"output directory already exists: {out_dir} (pass --force to overwrite generated files; non-generated files are preserved)")
    for rel_path, content in render_application_files(ctx).items():
        target = out_dir / rel_path
        if target.exists() and target.read_text(encoding="utf-8") != content:
            backup = out_dir / ".efw_backup" / rel_path
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        write_file(out_dir, rel_path, content)
