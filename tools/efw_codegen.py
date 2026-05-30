#!/usr/bin/env python3
"""Generate EFW application code from a graph JSON file.

The generator is still intentionally small, but it is no longer tied to a single
line-follower instance.  It supports multiple line-follower flows, periodic
custom tasks, custom sensors/algorithms/modules whose implementation lives in
`custom_files`, and generated application glue that schedules all configured
flows from a 1 ms tick.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SUPPORTED_NODE_TYPES = {
    "hal.gpio_line_input",
    "hal.custom",
    "sensor.line_tracking",
    "sensor.custom",
    "actuator.motor",
    "actuator.custom",
    "algorithm.pid",
    "algorithm.custom",
    "module.custom",
    "task.periodic",
    "project.module",
    "event.topic",
    "event.publisher",
    "event.subscriber",
    "state.machine",
    "state.state",
    "state.transition",
    "logic.if",
    "logic.loop",
    "custom.card",
    "custom.code",
}
SUPPORTED_FLOW_TYPES = {"control.line_follower"}
GENERATED_FILES = {
    "app_board_config.h",
    "app_manifest.h",
    "app_components.h",
    "app_components.c",
    "app_platform.h",
    "app_platform.c",
    "app_board_adapter.h",
    "app_bootstrap.h",
    "app_bootstrap.c",
    "main.c",
    "CMakeLists.generated.txt",
}


def c_ident(value: str, fallback: str = "app") -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", value or fallback)
    ident = re.sub(r"_+", "_", ident).strip("_") or fallback
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def macro_ident(value: str) -> str:
    return c_ident(value).upper()


def c_str(value: str | None) -> str:
    if value is None or value == "":
        return "0"
    return json.dumps(str(value))


def c_float(value) -> str:
    number = float(value)
    text = f"{number:.9g}"
    if "e" not in text and "." not in text:
        text += ".0"
    return f"{text}f"


def c_bool(value) -> str:
    return "1" if bool(value) else "0"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def node_type(nodes, node_id):
    node = nodes.get(node_id)
    return node.get("type") if node else None


def nodes_of(ctx, type_name):
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


def normalize_c_params(params: str) -> str:
    return re.sub(r"\s+", " ", params.replace("*", " * ")).strip()


def find_c_function_defs(files):
    definitions = {}
    pattern = re.compile(r"\befw_status_t\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{")
    for item in files:
        if not item["path"].endswith(".c"):
            continue
        for match in pattern.finditer(item["content"]):
            name = match.group(1)
            params = normalize_c_params(match.group(2))
            require(name not in definitions, f"duplicate custom function definition: {name}")
            definitions[name] = {"path": item["path"], "params": params}
    return definitions


def find_c_topic_callback_defs(files):
    definitions = {}
    pattern = re.compile(r"\bvoid\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{")
    for item in files:
        if not item["path"].endswith(".c"):
            continue
        for match in pattern.finditer(item["content"]):
            name = match.group(1)
            params = normalize_c_params(match.group(2))
            require(name not in definitions, f"duplicate custom topic callback definition: {name}")
            definitions[name] = {"path": item["path"], "params": params}
    return definitions



def find_c_condition_defs(files):
    definitions = {}
    pattern = re.compile(r"\b(?:int|uint8_t|bool)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{")
    for item in files:
        if not item["path"].endswith(".c"):
            continue
        for match in pattern.finditer(item["content"]):
            name = match.group(1)
            params = normalize_c_params(match.group(2))
            require(name not in definitions, f"duplicate custom condition definition: {name}")
            definitions[name] = {"path": item["path"], "params": params}
    return definitions

def validate_file_items(items, field_name):
    require(isinstance(items, list), f"{field_name} must be an array when present")
    result = []
    seen = set()
    for item in items:
        require(isinstance(item, dict), f"each {field_name} item must be an object")
        rel_path = item.get("path")
        content = item.get("content", "")
        require(isinstance(rel_path, str) and rel_path, f"{field_name} path must be a non-empty string")
        require(isinstance(content, str), f"{field_name} content must be a string: {rel_path}")
        path = Path(rel_path)
        require(not path.is_absolute(), f"{field_name} path must be relative: {rel_path}")
        require(".." not in path.parts, f"{field_name} path must not contain '..': {rel_path}")
        require(path.suffix in {".c", ".h", ".inc", ".md", ".txt"}, f"{field_name} extension is not allowed: {rel_path}")
        normalized = path.as_posix()
        require(normalized not in GENERATED_FILES, f"{field_name} must not overwrite generated file: {normalized}")
        require(normalized not in seen, f"duplicate {field_name} path: {normalized}")
        seen.add(normalized)
        if normalized.endswith(".c") and "efw_status_t" in content:
            has_include = '#include "efw/efw.h"' in content or "#include <efw/efw.h>" in content
            has_app_header = re.search(r'#include\s+"app_[A-Za-z0-9_./-]+\.h"', content) is not None
            require(has_include or has_app_header, f"{normalized} uses EFW symbols but does not include efw/efw.h or an app_*.h header")
        result.append({"path": normalized, "content": content})
    return result


def validate_custom_files(graph):
    custom_files = validate_file_items(graph.get("custom_files", []), "custom_files")
    board_files = validate_file_items(graph.get("board_adapters", []), "board_adapters")
    all_paths = {item["path"] for item in custom_files}
    for item in board_files:
        require(item["path"] not in all_paths, f"board_adapters path duplicates custom_files path: {item['path']}")
        all_paths.add(item["path"])
    return custom_files, board_files


def expected_callbacks(ctx):
    callbacks = {}

    def add(name, params, owner):
        if not name:
            return
        cname = c_ident(name)
        require(name == cname, f"{owner} callback must be a valid C identifier: {name}")
        existing = callbacks.get(cname)
        require(not existing or existing["params"] == params, f"callback {cname} is declared with incompatible signatures")
        callbacks[cname] = {"params": normalize_c_params(params), "owner": owner}

    for node in nodes_of(ctx, "hal.custom"):
        add(node.get("init"), "void *ctx", f"{node['id']}.init")
        add(node.get("read"), "void *ctx, void *buf, uint16_t len, uint16_t *actual", f"{node['id']}.read")
        add(node.get("write"), "void *ctx, const void *buf, uint16_t len, uint16_t *actual", f"{node['id']}.write")
        add(node.get("ioctl"), "void *ctx, uint32_t cmd, void *arg", f"{node['id']}.ioctl")
    for node in nodes_of(ctx, "sensor.custom"):
        add(node.get("init"), "void *ctx", f"{node['id']}.init")
        add(node.get("read"), "void *ctx, void *out", f"{node['id']}.read")
    for node in nodes_of(ctx, "actuator.custom"):
        add(node.get("init"), "void *ctx", f"{node['id']}.init")
        add(node.get("enable"), "void *ctx", f"{node['id']}.enable")
        add(node.get("disable"), "void *ctx", f"{node['id']}.disable")
        add(node.get("write"), "void *ctx, const void *cmd", f"{node['id']}.write")
    for node in nodes_of(ctx, "algorithm.custom"):
        add(node.get("run"), "void *ctx, const void *in, void *out", f"{node['id']}.run")
    for node in nodes_of(ctx, "module.custom"):
        for cb in ["init", "start", "stop", "poll"]:
            add(node.get(cb), "void *ctx", f"{node['id']}.{cb}")
    for task in ctx["tasks"]:
        add(task.get("call"), "void", f"task {task.get('id')}.call")
    for node in nodes_of(ctx, "state.state"):
        add(node.get("on_enter"), "void *ctx", f"{node['id']}.on_enter")
        add(node.get("on_update"), "void *ctx", f"{node['id']}.on_update")
        add(node.get("on_exit"), "void *ctx", f"{node['id']}.on_exit")
    for node in nodes_of(ctx, "logic.if"):
        add(node.get("then"), "void", f"{node['id']}.then")
        add(node.get("else"), "void", f"{node['id']}.else")
    for node in nodes_of(ctx, "logic.loop"):
        add(node.get("body"), "void", f"{node['id']}.body")
    return callbacks


def validate_callback_implementations(ctx):
    files = ctx["custom_files"] + ctx["board_adapters"]
    definitions = find_c_function_defs(files)
    topic_definitions = find_c_topic_callback_defs(files)
    condition_definitions = find_c_condition_defs(files)
    reserved = {"app_init", "app_loop_1ms", "app_loop_tick", "app_platform_register", "app_components_register", "main"}
    for item in files:
        for reserved_name in reserved:
            pattern = r"\b[A-Za-z_][A-Za-z0-9_\s\*]*\s+" + re.escape(reserved_name) + r"\s*\([^;]*\)\s*\{"
            require(re.search(pattern, item["content"]) is None, f"custom function conflicts with generated symbol: {reserved_name}")
    for name in definitions:
        require(name not in reserved, f"custom function conflicts with generated symbol: {name}")
    for name, spec in expected_callbacks(ctx).items():
        definition = definitions.get(name)
        require(definition, f"missing callback implementation for {spec['owner']}: {name}")
        require(definition["params"] == spec["params"], f"callback {name} in {definition['path']} has signature ({definition['params']}), expected ({spec['params']})")
    topic_params = normalize_c_params("uint16_t topic_id, const void *data, uint16_t size, void *user")
    for node in nodes_of(ctx, "event.subscriber"):
        callback = c_ident(node["callback"])
        definition = topic_definitions.get(callback)
        require(definition, f"missing topic subscriber callback implementation for {node['id']}: {callback}")
        require(definition["params"] == topic_params, f"topic callback {callback} in {definition['path']} has signature ({definition['params']}), expected ({topic_params})")
    for node in nodes_of(ctx, "state.transition") + nodes_of(ctx, "logic.if") + nodes_of(ctx, "logic.loop"):
        condition = node.get("condition")
        if condition:
            cname = c_ident(condition)
            require(condition == cname, f"{node['id']}.condition must be a valid C identifier")
            definition = condition_definitions.get(cname)
            require(definition, f"missing condition implementation for {node['id']}: {cname}")
            require(definition["params"] == "void", f"condition {cname} in {definition['path']} has signature ({definition['params']}), expected (void)")


def apply_edge_semantics(raw_edges, nodes_by_id):
    """Derive common node fields from generic graph.edges before validation.

    This keeps edges as a first-class graph input while preserving the current
    generator templates that still read node fields/flows for concrete C output.
    """
    for edge in raw_edges:
        src = nodes_by_id.get(edge.get("from"))
        dst = nodes_by_id.get(edge.get("to"))
        if not src or not dst:
            continue
        src_type = src.get("type")
        dst_type = dst.get("type")
        if src_type == "project.module" and dst_type != "project.module":
            dst.setdefault("module", src.get("id"))
        elif src_type == "hal.gpio_line_input" and dst_type == "sensor.line_tracking":
            dst.setdefault("input", src.get("id"))
        elif src_type == "hal.custom" and dst_type in {"sensor.custom", "actuator.custom"}:
            dst.setdefault("hal_name", src.get("id"))
        elif src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"}:
            dst.setdefault("topic", src.get("id"))
        elif src_type in {"module.custom", "sensor.custom", "sensor.line_tracking"} and dst_type == "event.publisher":
            dst.setdefault("source", src.get("id"))
        elif src_type == "event.subscriber" and dst_type == "module.custom":
            src.setdefault("target", dst.get("id"))
        elif src_type == "state.machine" and dst_type in {"state.state", "state.transition"}:
            dst.setdefault("machine", src.get("id"))
        elif src_type == "state.state" and dst_type == "state.transition":
            dst.setdefault("from", src.get("id"))
            dst.setdefault("machine", src.get("machine"))
        elif src_type == "state.transition" and dst_type == "state.state":
            src.setdefault("to", dst.get("id"))
            src.setdefault("machine", dst.get("machine"))
        elif src_type == "logic.if" and dst_type in {"task.periodic", "module.custom"}:
            dst.setdefault("call", f"app_logic_{c_ident(src.get('id', 'if'))}")
        elif src_type == "logic.loop" and dst_type in {"task.periodic", "module.custom"}:
            dst.setdefault("call", f"app_logic_{c_ident(src.get('id', 'loop'))}")


def validate_graph(graph):
    require(isinstance(graph, dict), "graph root must be an object")
    project = graph.get("project", {})
    require(isinstance(project, dict), "project must be an object")
    require(isinstance(project.get("name", "generated_app"), str), "project.name must be a string")
    tick_ms = int(project.get("tick_ms", 1))
    require(tick_ms > 0, "project.tick_ms must be > 0")

    board = graph.get("board", {})
    require(isinstance(board, dict), "board must be an object when present")
    if "profile" in board:
        require(isinstance(board.get("profile"), str), "board.profile must be a string")
    pin_plan = board.get("pin_plan", [])
    require(isinstance(pin_plan, list), "board.pin_plan must be an array when present")
    seen_board_pins = set()
    for index, pin in enumerate(pin_plan):
        require(isinstance(pin, dict), f"board.pin_plan[{index}] must be an object")
        require(isinstance(pin.get("node"), str) and pin.get("node"), f"board.pin_plan[{index}].node must be a non-empty string")
        require(isinstance(pin.get("usage", ""), str), f"board.pin_plan[{index}].usage must be a string")
        key = (pin.get("node"), pin.get("usage"), str(pin.get("port", "")), str(pin.get("pin", "")), str(pin.get("channel", "")))
        require(key not in seen_board_pins, f"duplicate board pin plan entry: {key}")
        seen_board_pins.add(key)

    raw_nodes = graph.get("nodes")
    raw_flows = graph.get("flows", [])
    raw_tasks = graph.get("tasks", [])
    raw_edges = graph.get("edges", [])
    require(isinstance(raw_nodes, list) and raw_nodes, "nodes must be a non-empty array")
    require(isinstance(raw_flows, list), "flows must be an array")
    require(isinstance(raw_tasks, list), "tasks must be an array when present")
    require(isinstance(raw_edges, list), "edges must be an array when present")

    nodes_by_id = {}
    for node in raw_nodes:
        require(isinstance(node, dict), "each node must be an object")
        node_id = node.get("id")
        node_type_name = node.get("type")
        require(isinstance(node_id, str) and node_id, "each node needs a non-empty string id")
        require(node_type_name in SUPPORTED_NODE_TYPES, f"unsupported node type for {node_id}: {node_type_name}")
        require(node_id not in nodes_by_id, f"duplicate node id: {node_id}")
        nodes_by_id[node_id] = node

    edge_ids = set()
    for index, edge in enumerate(raw_edges):
        require(isinstance(edge, dict), f"edges[{index}] must be an object")
        edge_id = edge.get("id", f"edge_{index}")
        require(edge_id not in edge_ids, f"duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        require(edge.get("from") in nodes_by_id, f"edge {edge_id}.from must reference an existing node")
        require(edge.get("to") in nodes_by_id, f"edge {edge_id}.to must reference an existing node")
    apply_edge_semantics(raw_edges, nodes_by_id)

    for node in raw_nodes:
        node_type_name = node["type"]
        if node_type_name == "hal.gpio_line_input":
            channels = int(node.get("channels", 0))
            require(channels > 0, f"{node['id']}.channels must be > 0")
            require(channels <= 8, f"{node['id']}.channels must be <= EFW_LINE_TRACKING_MAX_CHANNELS default 8")
            require(len(node.get("pins", [])) == channels, f"{node['id']}.pins length must equal channels")
        elif node_type_name == "hal.custom":
            require(node.get("init") or node.get("read") or node.get("write") or node.get("ioctl"), f"{node['id']} needs at least one HAL callback")
        elif node_type_name == "sensor.line_tracking":
            require(node.get("input") in nodes_by_id, f"{node['id']}.input must reference a HAL node")
            require(node_type(nodes_by_id, node.get("input")) == "hal.gpio_line_input", f"{node['id']}.input must be hal.gpio_line_input")
        elif node_type_name == "actuator.motor":
            require(isinstance(node.get("pwm"), dict), f"{node['id']}.pwm must be an object")
            require(isinstance(node.get("dir_pin"), dict), f"{node['id']}.dir_pin must be an object")
        elif node_type_name == "actuator.custom":
            require(node.get("write"), f"{node['id']}.write must name a custom write callback")
            if node.get("hal_name"):
                require(node.get("hal_name") in nodes_by_id and nodes_by_id[node.get("hal_name")]["type"].startswith("hal."), f"{node['id']}.hal_name must reference a HAL node")
        elif node_type_name == "sensor.custom":
            require(node.get("read"), f"{node['id']}.read must name a custom read callback")
            if node.get("hal_name"):
                require(node.get("hal_name") in nodes_by_id and nodes_by_id[node.get("hal_name")]["type"].startswith("hal."), f"{node['id']}.hal_name must reference a HAL node")
        elif node_type_name == "algorithm.custom":
            require(node.get("run"), f"{node['id']}.run must name a custom run callback")
        elif node_type_name == "project.module":
            require(isinstance(node.get("display_name", node["id"]), str), f"{node['id']}.display_name must be a string")
        elif node_type_name == "event.topic":
            topic_id = int(node.get("topic_id", -1))
            require(0 <= topic_id <= 65535, f"{node['id']}.topic_id must be 0..65535")
            require(isinstance(node.get("payload_type", "void"), str), f"{node['id']}.payload_type must be a string")
        elif node_type_name == "event.publisher":
            require(node.get("topic") in nodes_by_id and nodes_by_id[node.get("topic")]["type"] == "event.topic", f"{node['id']}.topic must reference event.topic")
            if node.get("source"):
                require(node.get("source") in nodes_by_id, f"{node['id']}.source must reference an existing node")
        elif node_type_name == "event.subscriber":
            require(node.get("topic") in nodes_by_id and nodes_by_id[node.get("topic")]["type"] == "event.topic", f"{node['id']}.topic must reference event.topic")
            if node.get("target"):
                require(node.get("target") in nodes_by_id, f"{node['id']}.target must reference an existing node")
            callback = node.get("callback")
            require(isinstance(callback, str) and callback == c_ident(callback), f"{node['id']}.callback must be a valid C identifier")
        elif node_type_name == "state.machine":
            require(isinstance(node.get("initial", ""), str), f"{node['id']}.initial must be a string")
        elif node_type_name == "state.state":
            require(node.get("machine") in nodes_by_id and nodes_by_id[node.get("machine")]["type"] == "state.machine", f"{node['id']}.machine must reference state.machine")
        elif node_type_name == "state.transition":
            require(node.get("machine") in nodes_by_id and nodes_by_id[node.get("machine")]["type"] == "state.machine", f"{node['id']}.machine must reference state.machine")
            require(node.get("from") in nodes_by_id and nodes_by_id[node.get("from")]["type"] == "state.state", f"{node['id']}.from must reference state.state")
            require(node.get("to") in nodes_by_id and nodes_by_id[node.get("to")]["type"] == "state.state", f"{node['id']}.to must reference state.state")
            require(nodes_by_id[node.get("from")].get("machine") == node.get("machine") and nodes_by_id[node.get("to")].get("machine") == node.get("machine"), f"{node['id']} endpoints must belong to the same state.machine")
            if node.get("condition"):
                require(node.get("condition") == c_ident(node.get("condition")), f"{node['id']}.condition must be a valid C identifier")
        elif node_type_name in {"logic.if", "logic.loop"}:
            require(isinstance(node.get("condition", ""), str), f"{node['id']}.condition must be a string")

    module_ids = {node["id"] for node in raw_nodes if node.get("type") == "project.module"}
    for node in raw_nodes:
        if node.get("module"):
            require(node.get("module") in module_ids, f"{node['id']}.module must reference project.module")

    flows = []
    flow_ids = set()
    for flow in raw_flows:
        require(isinstance(flow, dict), "each flow must be an object")
        require(flow.get("type") in SUPPORTED_FLOW_TYPES, f"unsupported flow type: {flow.get('type')}")
        flow_id = flow.get("id")
        require(isinstance(flow_id, str) and flow_id, "each flow needs a non-empty id")
        require(flow_id not in flow_ids, f"duplicate flow id: {flow_id}")
        flow_ids.add(flow_id)
        sensor = nodes_by_id.get(flow.get("sensor"))
        pid = nodes_by_id.get(flow.get("pid"))
        left_motor = nodes_by_id.get(flow.get("left_motor"))
        right_motor = nodes_by_id.get(flow.get("right_motor"))
        require(sensor and sensor.get("type") == "sensor.line_tracking", f"{flow_id}.sensor must reference sensor.line_tracking")
        require(pid and pid.get("type") in {"algorithm.pid", "algorithm.custom"}, f"{flow_id}.pid must reference algorithm.pid or algorithm.custom")
        if pid and pid.get("type") == "algorithm.custom":
            require(pid.get("io_contract") == "efw_pid", f"{flow_id}.pid custom algorithm must declare io_contract=efw_pid because LineFollower passes efw_pid_input_t and expects efw_pid_output_t")
        require(left_motor and left_motor.get("type") == "actuator.motor", f"{flow_id}.left_motor must reference actuator.motor")
        require(right_motor and right_motor.get("type") == "actuator.motor", f"{flow_id}.right_motor must reference actuator.motor")
        input_node = nodes_by_id[sensor["input"]]
        require(len(flow.get("weights", [])) == int(input_node["channels"]), f"{flow_id}.weights length must match sensor channels")
        require(float(flow.get("dt", 0.001)) > 0.0, f"{flow_id}.dt must be > 0")
        period_ms = int(flow.get("period_ms", tick_ms))
        require(period_ms > 0, f"{flow_id}.period_ms must be > 0")
        require(period_ms % tick_ms == 0, f"{flow_id}.period_ms must be a multiple of project.tick_ms")
        flows.append(flow)

    tasks = []
    task_ids = set()
    flow_ids_known = {flow["id"] for flow in flows}
    for item in raw_tasks + [node for node in raw_nodes if node.get("type") == "task.periodic"]:
        require(isinstance(item, dict), "each task must be an object")
        require(item.get("type", "task.periodic") == "task.periodic", f"unsupported task type: {item.get('type')}")
        task_id = item.get("id")
        require(isinstance(task_id, str) and task_id, "each task needs a non-empty id")
        require(task_id not in task_ids, f"duplicate task id: {task_id}")
        task_ids.add(task_id)
        require(item.get("call") or item.get("flow"), f"task {item.get('id')} needs call or flow")
        if item.get("flow"):
            require(item.get("flow") in flow_ids_known, f"task {task_id}.flow must reference an existing flow id")
        task_period = int(item.get("period_ms", tick_ms))
        require(task_period > 0, f"task {item.get('id')}.period_ms must be > 0")
        require(task_period % tick_ms == 0, f"task {task_id}.period_ms must be a multiple of project.tick_ms")
        tasks.append(item)

    custom_files, board_adapters = validate_custom_files(graph)
    ctx = {
        "project": project,
        "board": board,
        "nodes": raw_nodes,
        "nodes_by_id": nodes_by_id,
        "flows": flows,
        "tasks": tasks,
        "edges": raw_edges,
        "custom_files": custom_files,
        "board_adapters": board_adapters,
    }
    validate_callback_implementations(ctx)
    return ctx


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
    return "\n".join(lines)


def event_topic_id(ctx, topic_ref):
    topic = ctx["nodes_by_id"].get(topic_ref)
    return int(topic.get("topic_id", 0)) if topic else 0


def render_manifest(ctx):
    return f"""
/**
 * @file    app_manifest.h
 * @brief   Generated feature switches and registry capacities.
 */

#ifndef APP_MANIFEST_H
#define APP_MANIFEST_H

#include "app_board_config.h"

#define APP_USE_HAL                 {c_bool(len(nodes_of(ctx, 'hal.gpio_line_input') + nodes_of(ctx, 'hal.custom')))}
#define APP_USE_SENSOR              {c_bool(len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom')))}
#define APP_USE_LINE_TRACKING       {c_bool(len(nodes_of(ctx, 'sensor.line_tracking')))}
#define APP_USE_ACTUATOR            {c_bool(len(nodes_of(ctx, 'actuator.motor') + nodes_of(ctx, 'actuator.custom')))}
#define APP_USE_MOTOR               {c_bool(len(nodes_of(ctx, 'actuator.motor')))}
#define APP_USE_ALGORITHM           {c_bool(len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom')))}
#define APP_USE_PID                 {c_bool(len(nodes_of(ctx, 'algorithm.pid')))}
#define APP_USE_MODULE              {c_bool(len(nodes_of(ctx, 'module.custom')))}
#define APP_USE_EVENT               {c_bool(len(nodes_of(ctx, 'event.topic') + nodes_of(ctx, 'event.publisher') + nodes_of(ctx, 'event.subscriber')))}
#define APP_USE_STATE_MACHINE       {c_bool(len(nodes_of(ctx, 'state.machine') + nodes_of(ctx, 'state.state') + nodes_of(ctx, 'state.transition')))}
#define APP_USE_LOGIC               {c_bool(len(nodes_of(ctx, 'logic.if') + nodes_of(ctx, 'logic.loop')))}

#define APP_PROJECT_TICK_MS          {int(ctx["project"].get("tick_ms", 1))}u

#define APP_HAL_COUNT               {len(nodes_of(ctx, 'hal.gpio_line_input') + nodes_of(ctx, 'hal.custom'))}
#define APP_SENSOR_COUNT            {len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom'))}
#define APP_ACTUATOR_COUNT          {len(nodes_of(ctx, 'actuator.motor') + nodes_of(ctx, 'actuator.custom'))}
#define APP_ALGO_COUNT              {len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom'))}
#define APP_MODULE_COUNT            {len(nodes_of(ctx, 'module.custom'))}
#define APP_TOPIC_COUNT             {len(nodes_of(ctx, 'event.topic'))}
#define APP_STATE_COUNT             {len(nodes_of(ctx, 'state.state'))}
#define APP_LOGIC_COUNT             {len(nodes_of(ctx, 'logic.if') + nodes_of(ctx, 'logic.loop'))}

{render_topic_macros(ctx)}
#endif
"""


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


def render_components_c(ctx):
    parts = ["""
/**
 * @file    app_components.c
 * @brief   Generated algorithm and module registration.
 */

#include "app_components.h"
#include "app_manifest.h"

"""]
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
    parts.append("efw_status_t app_components_register(void) {\n    efw_status_t s;\n")
    for node in nodes_of(ctx, "algorithm.pid") + nodes_of(ctx, "algorithm.custom"):
        parts.append(f"    s = efw_algo_register(&g_{c_ident(node['id'])}_algo);\n    if (s != EFW_OK) return s;\n")
    for node in nodes_of(ctx, "module.custom"):
        parts.append(f"    s = efw_module_register(&g_{c_ident(node['id'])}_module);\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n")
    return "".join(parts)


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


def render_platform_c(ctx):
    line_inputs = nodes_of(ctx, "hal.gpio_line_input")
    custom_hals = nodes_of(ctx, "hal.custom")
    line_sensors = nodes_of(ctx, "sensor.line_tracking")
    custom_sensors = nodes_of(ctx, "sensor.custom")
    motors = nodes_of(ctx, "actuator.motor")
    custom_actuators = nodes_of(ctx, "actuator.custom")
    parts = ["""
/**
 * @file    app_platform.c
 * @brief   Generated platform layer. Replace mock read/write internals with BSP calls.
 */

#include "app_platform.h"
#include "app_manifest.h"

#ifndef EFW_NULL_NAME
#define EFW_NULL_NAME 0
#endif

"""]
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
    /* TODO(real board): speed -> PWM duty, direction -> GPIO level. */
    motor->last_speed = motor_cmd->speed;
    motor->last_direction = motor_cmd->direction;
    return EFW_OK;
}

""")
    for node in custom_hals:
        for cb, sig in [("init", "void *ctx"), ("read", "void *ctx, void *buf, uint16_t len, uint16_t *actual"), ("write", "void *ctx, const void *buf, uint16_t len, uint16_t *actual"), ("ioctl", "void *ctx, uint32_t cmd, void *arg")]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}({sig});\n")
    for node in custom_actuators:
        parts.append(f"extern efw_status_t {c_ident(node['write'])}(void *ctx, const void *cmd);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
        if node.get("enable"):
            parts.append(f"extern efw_status_t {c_ident(node['enable'])}(void *ctx);\n")
        if node.get("disable"):
            parts.append(f"extern efw_status_t {c_ident(node['disable'])}(void *ctx);\n")
    for node in custom_sensors:
        parts.append(f"extern efw_status_t {c_ident(node['read'])}(void *ctx, void *out);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
    for node in line_inputs:
        ident = c_ident(node["id"])
        macro = macro_ident(node["id"])
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
    for node in custom_hals:
        ident = c_ident(node["id"])
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
    for node in line_sensors:
        ident = c_ident(node["id"])
        input_node = ctx["nodes_by_id"][node["input"]]
        parts.append(f"""static efw_sensor_ops_t g_{ident}_sensor = {{
    .name = {c_str(node['id'])},
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = {int(input_node['channels'])}u,
    .hal_name = {c_str(node['input'])},
    .ctx = (void *){c_str(node['input'])},
    .read = line_sensor_read,
}};

""")
    for node in custom_sensors:
        ident = c_ident(node["id"])
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
    for node in motors:
        ident = c_ident(node["id"])
        macro = macro_ident(node["id"])
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
    for node in custom_actuators:
        ident = c_ident(node["id"])
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
    parts.append("efw_status_t app_platform_register(void) {\n    efw_status_t s;\n")
    for node in line_inputs + custom_hals:
        parts.append(f"    s = efw_hal_register(&g_{c_ident(node['id'])}_hal);\n    if (s != EFW_OK) return s;\n")
    for node in line_sensors + custom_sensors:
        parts.append(f"    s = efw_sensor_register(&g_{c_ident(node['id'])}_sensor);\n    if (s != EFW_OK) return s;\n")
    for node in motors:
        parts.append(f"    s = efw_actuator_register(&g_{c_ident(node['id'])}_motor);\n    if (s != EFW_OK) return s;\n")
    for node in custom_actuators:
        parts.append(f"    s = efw_actuator_register(&g_{c_ident(node['id'])}_actuator);\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    parts.append("void app_platform_set_line_state(const char *input_name, const uint16_t *values, uint8_t count) {\n    if (!input_name || !values) return;\n")
    for node in line_inputs:
        ident = c_ident(node["id"])
        parts.append(f"    if (app_name_eq(input_name, {c_str(node['id'])})) {{\n        uint8_t n = (count < g_{ident}_ctx.channel_count) ? count : g_{ident}_ctx.channel_count;\n        for (uint8_t i = 0; i < n; ++i) g_{ident}_ctx.channel[i] = values[i];\n        return;\n    }}\n")
    parts.append("}\n")
    return "".join(parts)


def render_bootstrap_h():
    return """
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

#endif
"""



def states_by_machine(ctx):
    result = {}
    for machine in nodes_of(ctx, "state.machine"):
        states = [node for node in nodes_of(ctx, "state.state") if node.get("machine") == machine["id"]]
        transitions = [node for node in nodes_of(ctx, "state.transition") if node.get("machine") == machine["id"]]
        result[machine["id"]] = {"machine": machine, "states": states, "transitions": transitions}
    return result


def render_state_logic_blocks(ctx):
    parts = []
    machines = states_by_machine(ctx)
    if machines or nodes_of(ctx, "logic.if") or nodes_of(ctx, "logic.loop"):
        parts.append("static efw_status_t app_noop_status(void *ctx) { EFW_UNUSED(ctx); return EFW_OK; }\n")
    for node in nodes_of(ctx, "state.state"):
        for cb, sig in [("on_enter", "void *ctx"), ("on_update", "void *ctx"), ("on_exit", "void *ctx")]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}({sig});\n")
    for node in nodes_of(ctx, "state.transition"):
        if node.get("condition"):
            parts.append(f"extern int {c_ident(node['condition'])}(void);\n")
    for node in nodes_of(ctx, "logic.if"):
        if node.get("condition"):
            parts.append(f"extern int {c_ident(node['condition'])}(void);\n")
        for cb in ["then", "else"]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}(void);\n")
    for node in nodes_of(ctx, "logic.loop"):
        if node.get("condition"):
            parts.append(f"extern int {c_ident(node['condition'])}(void);\n")
        if node.get("body"):
            parts.append(f"extern efw_status_t {c_ident(node['body'])}(void);\n")
    if parts:
        parts.append("\n")
    for mid, bundle in machines.items():
        m_ident = c_ident(mid)
        states = bundle["states"]
        index = {state["id"]: i for i, state in enumerate(states)}
        for state in states:
            s_ident = c_ident(state["id"])
            parts.append(f"static efw_state_machine_ops_t g_state_{s_ident} = {{\n")
            parts.append(f"    .name = {c_str(state['id'])},\n    .ctx = 0,\n")
            parts.append(f"    .on_enter = {c_ident(state['on_enter']) if state.get('on_enter') else '0'},\n")
            parts.append(f"    .on_tick = {c_ident(state['on_update']) if state.get('on_update') else 'app_noop_status'},\n")
            parts.append(f"    .on_exit = {c_ident(state['on_exit']) if state.get('on_exit') else '0'},\n}};\n")
        parts.append(f"static efw_state_machine_ops_t *g_{m_ident}_states[] = {{ {', '.join('&g_state_' + c_ident(s['id']) for s in states)} }};\n")
        initial = bundle["machine"].get("initial") or (states[0]["id"] if states else "")
        parts.append(f"static uint8_t g_{m_ident}_current = {index.get(initial, 0)}u;\n")
        parts.append(f"static efw_status_t app_{m_ident}_register(void) {{\n    efw_status_t s;\n")
        for state in states:
            parts.append(f"    s = efw_sm_register(&g_state_{c_ident(state['id'])});\n    if (s != EFW_OK) return s;\n")
        if states:
            parts.append(f"    if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
        parts.append("    return EFW_OK;\n}\n")
        parts.append(f"static efw_status_t app_{m_ident}_tick(void) {{\n    efw_status_t s;\n")
        if states:
            parts.append(f"    s = g_{m_ident}_states[g_{m_ident}_current]->on_tick(g_{m_ident}_states[g_{m_ident}_current]->ctx);\n    if (s != EFW_OK) return s;\n")
            for transition in bundle["transitions"]:
                cond = c_ident(transition["condition"]) + "()" if transition.get("condition") else "1"
                from_idx = index.get(transition.get("from"), 0)
                to_idx = index.get(transition.get("to"), 0)
                parts.append(f"    if (g_{m_ident}_current == {from_idx}u && ({cond})) {{\n")
                parts.append(f"        if (g_{m_ident}_states[g_{m_ident}_current]->on_exit) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_exit(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
                parts.append(f"        g_{m_ident}_current = {to_idx}u;\n")
                parts.append(f"        if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n    }}\n")
        parts.append("    return EFW_OK;\n}\n\n")
    for node in nodes_of(ctx, "logic.if"):
        ident = c_ident(node["id"])
        cond = c_ident(node["condition"]) + "()" if node.get("condition") else "1"
        parts.append(f"static efw_status_t app_logic_{ident}(void) {{\n    efw_status_t s;\n    if ({cond}) {{\n")
        if node.get("then"):
            parts.append(f"        s = {c_ident(node['then'])}();\n        if (s != EFW_OK) return s;\n")
        parts.append("    } else {\n")
        if node.get("else"):
            parts.append(f"        s = {c_ident(node['else'])}();\n        if (s != EFW_OK) return s;\n")
        parts.append("    }\n    return EFW_OK;\n}\n\n")
    for node in nodes_of(ctx, "logic.loop"):
        ident = c_ident(node["id"])
        cond = c_ident(node["condition"]) + "()" if node.get("condition") else "1"
        max_iter = int(node.get("max_iterations", 1))
        parts.append(f"static efw_status_t app_logic_{ident}(void) {{\n    efw_status_t s;\n    uint16_t guard = 0u;\n    while (({cond}) && guard++ < {max_iter}u) {{\n")
        if node.get("body"):
            parts.append(f"        s = {c_ident(node['body'])}();\n        if (s != EFW_OK) return s;\n")
        parts.append("    }\n    return EFW_OK;\n}\n\n")
    return "".join(parts)

def render_bootstrap_c(ctx):
    parts = ["""
/**
 * @file    app_bootstrap.c
 * @brief   Generated runtime glue, flow bind, and 1 ms scheduler.
 */

#include "app_bootstrap.h"

#include "app_components.h"
#include "app_manifest.h"
#include "app_platform.h"
#include "efw/app/runtime.h"

#if APP_USE_HAL
static const efw_hal_ops_t *g_hal_pool[APP_HAL_COUNT];
#endif
#if APP_USE_SENSOR
static const efw_sensor_ops_t *g_sensor_pool[APP_SENSOR_COUNT];
#endif
#if APP_USE_ACTUATOR
static const efw_actuator_ops_t *g_actuator_pool[APP_ACTUATOR_COUNT];
#endif
#if APP_USE_ALGORITHM
static const efw_algo_ops_t *g_algo_pool[APP_ALGO_COUNT];
#endif
#if APP_USE_MODULE
static const efw_module_ops_t *g_module_pool[APP_MODULE_COUNT];
#endif

static uint32_t g_app_elapsed_ms;

"""]
    parts.append(render_state_logic_blocks(ctx))
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        weights = ", ".join(c_float(value) for value in flow["weights"])
        parts.append(f"static efw_line_follower_t g_{ident};\n")
        parts.append(f"static const float g_{ident}_weights[] = {{ {weights} }};\n")
    parts.append("\n")
    for task in ctx["tasks"]:
        if task.get("call"):
            parts.append(f"extern efw_status_t {c_ident(task['call'])}(void);\n")
    for node in nodes_of(ctx, "event.subscriber"):
        parts.append(f"extern void {c_ident(node['callback'])}(uint16_t topic_id, const void *data, uint16_t size, void *user);\n")
    parts.append("""
static efw_status_t app_init_pools(void) {
    efw_status_t s;
#if APP_USE_HAL
    s = efw_hal_registry_init_pool(g_hal_pool, APP_HAL_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_SENSOR
    s = efw_sensor_registry_init_pool(g_sensor_pool, APP_SENSOR_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_ACTUATOR
    s = efw_actuator_registry_init_pool(g_actuator_pool, APP_ACTUATOR_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_ALGORITHM
    s = efw_algo_registry_init_pool(g_algo_pool, APP_ALGO_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_MODULE
    s = efw_module_registry_init_pool(g_module_pool, APP_MODULE_COUNT);
    if (s != EFW_OK) return s;
#endif
    return EFW_OK;
}

static efw_status_t app_bind_handles(void) {
    efw_status_t s;
""")
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        parts.append(f"""    const efw_line_follower_config_t {ident}_config = {{
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
        parts.append(f"    s = efw_topic_subscribe({event_topic_id(ctx, node['topic'])}u, {c_ident(node['callback'])}, {node.get('user', '0')});\n    if (s != EFW_OK) return s;\n")
    for machine_id in states_by_machine(ctx):
        parts.append(f"    s = app_{c_ident(machine_id)}_register();\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    parts.append("static efw_status_t app_update_1ms(void) {\n    efw_status_t s;\n    g_app_elapsed_ms += APP_PROJECT_TICK_MS;\n")
    flow_tasks = {task.get("flow") for task in ctx["tasks"] if task.get("flow")}
    for flow in ctx["flows"]:
        if flow["id"] in flow_tasks:
            continue
        ident = c_ident(flow["id"])
        period = int(flow.get("period_ms", ctx["project"].get("tick_ms", 1)))
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = efw_line_follower_update(&g_{ident}, 0, 0);\n        if (s != EFW_OK) return s;\n    }}\n")
    for task in ctx["tasks"]:
        period = int(task.get("period_ms", ctx["project"].get("tick_ms", 1)))
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        if task.get("call"):
            parts.append(f"    if ({condition}) {{\n        s = {c_ident(task['call'])}();\n        if (s != EFW_OK) return s;\n    }}\n")
        elif task.get("flow"):
            ident = c_ident(task["flow"])
            parts.append(f"    if ({condition}) {{\n        s = efw_line_follower_update(&g_{ident}, 0, 0);\n        if (s != EFW_OK) return s;\n    }}\n")
    for machine_id in states_by_machine(ctx):
        parts.append(f"    s = app_{c_ident(machine_id)}_tick();\n    if (s != EFW_OK) return s;\n")
    for node in nodes_of(ctx, "logic.if") + nodes_of(ctx, "logic.loop"):
        period = int(node.get("period_ms", ctx["project"].get("tick_ms", 1)))
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = app_logic_{c_ident(node['id'])}();\n        if (s != EFW_OK) return s;\n    }}\n")
    if nodes_of(ctx, "module.custom"):
        parts.append("    s = efw_module_poll_all();\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    parts.append("""static const efw_app_manifest_t g_app_manifest = {
    .init_pools = app_init_pools,
    .register_platform = app_platform_register,
    .register_components = app_components_register,
    .bind_handles = app_bind_handles,
    .update_1ms = app_update_1ms,
};

efw_status_t app_init(void) {
    efw_status_t s = efw_app_init(&g_app_manifest);
    if (s != EFW_OK) return s;
#if APP_USE_MODULE
    s = efw_module_init_all();
    if (s != EFW_OK) return s;
    s = efw_module_start_all();
    if (s != EFW_OK) return s;
#endif
    return EFW_OK;
}

efw_status_t app_loop_tick(void) {
    return efw_app_update_1ms(&g_app_manifest);
}

efw_status_t app_loop_1ms(void) {
    return app_loop_tick();
}
""")
    return "".join(parts)


def first_line_input(ctx):
    line_inputs = nodes_of(ctx, "hal.gpio_line_input")
    return line_inputs[0] if line_inputs else None


def render_main_c(ctx):
    line_input = first_line_input(ctx)
    if line_input:
        channels = int(line_input["channels"])
        centered = ["0"] * channels
        centered[channels // 2] = "1"
        setup = f"""    const uint16_t centered_line[{channels}] = {{ {', '.join(centered)} }};
    app_platform_set_line_state({c_str(line_input['id'])}, centered_line, {channels}u);
"""
    else:
        setup = ""
    return f"""
/**
 * @file    main.c
 * @brief   Generated host-checkable entry point.
 */

#include "app_bootstrap.h"
#include "app_platform.h"

int main(void) {{
    app_init();
{setup}    app_loop_1ms();
    return 0;
}}
"""


def render_cmake(ctx):
    target = c_ident(ctx["project"].get("name", "generated_app"))
    custom_c_files = [item["path"] for item in ctx["custom_files"] + ctx["board_adapters"] if item["path"].endswith(".c")]
    custom_sources = "".join(f"    {path}\n" for path in custom_c_files)
    return f"""
# Optional generated-app CMake snippet.
add_executable(efw_app_{target}
    main.c
    app_bootstrap.c
    app_components.c
    app_platform.c
{custom_sources})
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
        "app_bootstrap.h": render_bootstrap_h(),
        "app_bootstrap.c": render_bootstrap_c(ctx),
        "main.c": render_main_c(ctx),
        "CMakeLists.generated.txt": render_cmake(ctx),
    }
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
        if not target.exists():
            status = "create"
        elif target.read_text(encoding="utf-8") == content:
            status = "same"
        else:
            status = "overwrite"
        preview.append({"path": rel_path, "status": status})
    if out_dir.exists():
        generated_set = set(files)
        for target in sorted(path for path in out_dir.rglob("*") if path.is_file()):
            rel = target.relative_to(out_dir).as_posix()
            if rel not in generated_set:
                preview.append({"path": rel, "status": "preserve"})
    return preview


def generate(graph_path: Path, out_dir: Path, force: bool) -> None:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = validate_graph(graph)
    if out_dir.exists() and any(out_dir.iterdir()):
        require(force, f"output directory already exists: {out_dir} (pass --force to overwrite generated files; non-generated files are preserved)")
    for rel_path, content in render_application_files(ctx).items():
        write_file(out_dir, rel_path, content)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Generate an EFW application from a graph JSON file.")
    parser.add_argument("graph", type=Path, help="path to graph JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output application directory")
    parser.add_argument("--force", action="store_true", help="replace output directory if it already exists")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    try:
        generate(args.graph, args.output, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"efw-codegen: {exc}", file=sys.stderr)
        return 1
    print(f"generated EFW application: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
