"""Graph validation for EFW code generation.

This module is intentionally free of rendering code. It validates the Graph
contract and returns the normalized context consumed by render/preview/generate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from codegen.graph import CALLBACK_RETURNS, CALLBACK_SIGNATURES, GENERATED_FILES, NODE_CONTRACTS, SUPPORTED_FLOW_TYPES, SUPPORTED_NODE_TYPES, VALID_EDGE_KINDS, apply_pair_semantics, node_generation_label


def c_ident(value: str, fallback: str = "app") -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", value or fallback)
    ident = re.sub(r"_+", "_", ident).strip("_") or fallback
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def node_type(nodes: dict[str, dict[str, Any]], node_id: str | None) -> str | None:
    node = nodes.get(node_id)
    return node.get("type") if node else None


def nodes_of(ctx: dict[str, Any], type_name: str) -> list[dict[str, Any]]:
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


def validate_contract_fields(node: dict[str, Any]) -> None:
    contract = NODE_CONTRACTS[node["type"]]
    for field in contract.get("required", []):
        require(node.get(field) not in (None, "", []), f"{node['id']}.{field} is required by {node['type']} ({node_generation_label(node['type'])})")
    required_any = contract.get("required_any", [])
    if required_any:
        require(any(node.get(field) not in (None, "", []) for field in required_any), f"{node['id']} needs at least one of {', '.join(required_any)} by {node['type']} ({node_generation_label(node['type'])})")


def normalize_c_params(params: str) -> str:
    return re.sub(r"\s+", " ", params.replace("*", " * ")).strip()


def find_c_function_defs(files: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    definitions = {}
    pattern = re.compile(r"\b(efw_status_t)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{")
    for item in files:
        if not item["path"].endswith(".c"):
            continue
        for match in pattern.finditer(item["content"]):
            return_type = match.group(1)
            name = match.group(2)
            params = normalize_c_params(match.group(3))
            require(name not in definitions, f"duplicate custom function definition: {name}")
            definitions[name] = {"path": item["path"], "params": params, "return": return_type}
    return definitions


def find_c_topic_callback_defs(files: list[dict[str, str]]) -> dict[str, dict[str, str]]:
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


def find_c_condition_defs(files: list[dict[str, str]]) -> dict[str, dict[str, str]]:
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


def validate_file_items(items: Any, field_name: str) -> list[dict[str, str]]:
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


def validate_custom_files(graph: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    custom_files = validate_file_items(graph.get("custom_files", []), "custom_files")
    board_files = validate_file_items(graph.get("board_adapters", []), "board_adapters")
    all_paths = {item["path"] for item in custom_files}
    for item in board_files:
        require(item["path"] not in all_paths, f"board_adapters path duplicates custom_files path: {item['path']}")
        all_paths.add(item["path"])
    return custom_files, board_files


def expected_callbacks(ctx: dict[str, Any]) -> dict[str, dict[str, str]]:
    callbacks = {}

    def add(name: str | None, signature_key: str, owner: str) -> None:
        if not name:
            return
        params = CALLBACK_SIGNATURES[signature_key]
        cname = c_ident(name)
        require(name == cname, f"{owner} callback must be a valid C identifier: {name}")
        existing = callbacks.get(cname)
        require(not existing or existing["params"] == params, f"callback {cname} is declared with incompatible signatures")
        callbacks[cname] = {"params": normalize_c_params(params), "owner": owner, "return": CALLBACK_RETURNS.get(signature_key, "efw_status_t")}

    for node in ctx["nodes"]:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        for field, signature_key in contract.get("callbacks", {}).items():
            if signature_key in {"topic.callback", "condition"}:
                continue
            add(node.get(field), signature_key, f"{node['id']}.{field}")
    for task in ctx["tasks"]:
        add(task.get("call"), "task.call", f"task {task.get('id')}.call")
    return callbacks


def validate_callback_implementations(ctx: dict[str, Any]) -> None:
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
        require(definition["return"] == spec["return"], f"callback {name} in {definition['path']} returns {definition['return']}, expected {spec['return']}")
        require(definition["params"] == spec["params"], f"callback {name} in {definition['path']} has signature ({definition['params']}), expected ({spec['params']})")
    topic_params = normalize_c_params(CALLBACK_SIGNATURES["topic.callback"])
    for node in nodes_of(ctx, "event.subscriber"):
        callback = c_ident(node["callback"])
        definition = topic_definitions.get(callback)
        require(definition, f"missing topic subscriber callback implementation for {node['id']}: {callback}")
        require(definition["params"] == topic_params, f"topic callback {callback} in {definition['path']} has signature ({definition['params']}), expected ({topic_params})")
    for node in nodes_of(ctx, "state.transition"):
        condition = node.get("condition")
        if condition:
            cname = c_ident(condition)
            require(condition == cname, f"{node['id']}.condition must be a valid C identifier")
            definition = condition_definitions.get(cname)
            require(definition, f"missing condition implementation for {node['id']}: {cname}")
            require(definition["params"] == CALLBACK_SIGNATURES["condition"], f"condition {cname} in {definition['path']} has signature ({definition['params']}), expected ({CALLBACK_SIGNATURES['condition']})")


def apply_edge_semantics(raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    graph_view = {"nodes": list(nodes_by_id.values()), "flows": []}
    for edge in raw_edges:
        src = nodes_by_id.get(edge.get("from"))
        dst = nodes_by_id.get(edge.get("to"))
        if not src or not dst:
            continue
        apply_pair_semantics(src, dst, graph_view, c_ident_func=c_ident, overwrite=False)


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
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
        kind = edge.get("kind", "generic")
        require(kind in VALID_EDGE_KINDS, f"edge {edge_id}.kind has unsupported semantic kind: {kind}")
    apply_edge_semantics(raw_edges, nodes_by_id)

    for node in raw_nodes:
        validate_contract_fields(node)
        node_type_name = node["type"]
        if node_type_name == "hal.gpio_line_input":
            channels = int(node.get("channels", 0))
            require(channels > 0, f"{node['id']}.channels must be > 0")
            require(channels <= 8, f"{node['id']}.channels must be <= EFW_LINE_TRACKING_MAX_CHANNELS default 8")
            require(len(node.get("pins", [])) == channels, f"{node['id']}.pins length must equal channels")
        elif node_type_name == "sensor.line_tracking":
            require(node.get("input") in nodes_by_id, f"{node['id']}.input must reference a HAL node")
            require(node_type(nodes_by_id, node.get("input")) == "hal.gpio_line_input", f"{node['id']}.input must be hal.gpio_line_input")
        elif node_type_name == "actuator.motor":
            require(isinstance(node.get("pwm"), dict), f"{node['id']}.pwm must be an object")
            require(isinstance(node.get("dir_pin"), dict), f"{node['id']}.dir_pin must be an object")
        elif node_type_name in {"actuator.custom", "sensor.custom"}:
            if node.get("hal_name"):
                require(node.get("hal_name") in nodes_by_id and nodes_by_id[node.get("hal_name")]["type"].startswith("hal."), f"{node['id']}.hal_name must reference a HAL node")
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
            condition = str(node.get("condition", "")).strip()
            require(condition, f"{node['id']}.condition must be a non-empty C condition callback")
            require(condition == c_ident(condition), f"{node['id']}.condition must be a valid C identifier")
            if node.get("action"):
                require(node.get("action") == c_ident(node.get("action")), f"{node['id']}.action must be a valid C identifier")
            require(int(node.get("priority", 0)) >= 0, f"{node['id']}.priority must be >= 0")
            require(int(node.get("timeout_ms", 0)) >= 0, f"{node['id']}.timeout_ms must be >= 0")
            require(isinstance(node.get("event_trigger", ""), str), f"{node['id']}.event_trigger must be a string")
        elif node_type_name == "processor.custom":
            process = node.get("process")
            require(isinstance(process, str) and process == c_ident(process), f"{node['id']}.process must be a valid C identifier")
            require(isinstance(node.get("input_contract", "custom"), str), f"{node['id']}.input_contract must be a string")
            require(isinstance(node.get("output_contract", "custom"), str), f"{node['id']}.output_contract must be a string")

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
