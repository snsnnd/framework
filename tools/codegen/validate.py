"""Graph validation for EFW code generation.

This module is intentionally free of rendering code. It validates the Graph
contract and returns the normalized context consumed by render/preview/generate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from .utils import c_ident, require, nodes_of, BUILTIN_CONTRACTS
    from .graph import CALLBACK_RETURNS, CALLBACK_SIGNATURES, GENERATED_FILES, NODE_CONTRACTS, SUPPORTED_FLOW_TYPES, SUPPORTED_NODE_TYPES, VALID_EDGE_KINDS, MULTI_INPUT_NODE_PORTS, TRIGGER_POLICY_CHOICES, OUTPUT_MODE_CHOICES, PROCESS_MODE_CHOICES, FIELD_MAPPING_SOURCE_CHOICES, FIELD_MAPPING_TRANSFORM_CHOICES, BUILTIN_STRUCT_FIELD_TYPES, apply_pair_semantics, node_generation_label
except ImportError:  # pragma: no cover - supports legacy top-level codegen imports
    from codegen.utils import c_ident, require, nodes_of, BUILTIN_CONTRACTS
    from codegen.graph import CALLBACK_RETURNS, CALLBACK_SIGNATURES, GENERATED_FILES, NODE_CONTRACTS, SUPPORTED_FLOW_TYPES, SUPPORTED_NODE_TYPES, VALID_EDGE_KINDS, MULTI_INPUT_NODE_PORTS, TRIGGER_POLICY_CHOICES, OUTPUT_MODE_CHOICES, PROCESS_MODE_CHOICES, FIELD_MAPPING_SOURCE_CHOICES, FIELD_MAPPING_TRANSFORM_CHOICES, BUILTIN_STRUCT_FIELD_TYPES, apply_pair_semantics, node_generation_label


def node_type(nodes: dict[str, dict[str, Any]], node_id: str | None) -> str | None:
    node = nodes.get(node_id)
    return node.get("type") if node else None


SINGLE_INPUT_PORT_RULES: dict[str, set[str]] = {
    "event.publisher": {"topic", "event_source"},
    "event.subscriber": {"topic", "event"},
    "sensor.line_tracking": {"hal"},
    "sensor.custom": {"hal"},
    "actuator.custom": {"hal", "control"},
    "algorithm.pid": {"sensor", "processor"},
    "algorithm.custom": {"sensor", "processor", "event"},
    "processor.custom": {"sensor", "algorithm", "event", "module_input"},
    "state.machine": {"state_machine"},
    "state.transition": {"state_machine", "transition_from"},
}


BUILTIN_STRUCT_FIELDS: dict[str, set[str]] = {name: set(fields.keys()) for name, fields in BUILTIN_STRUCT_FIELD_TYPES.items()}

PROCESSOR_INPUT_PORTS: tuple[str, ...] = tuple(MULTI_INPUT_NODE_PORTS["processor.custom"])
ALGORITHM_INPUT_PORTS: tuple[str, ...] = tuple(MULTI_INPUT_NODE_PORTS["algorithm.custom"])
MULTI_INPUT_PORTS: dict[str, tuple[str, ...]] = {key: tuple(value) for key, value in MULTI_INPUT_NODE_PORTS.items()}


def node_input_spec(node: dict[str, Any], port: str | None = None) -> dict[str, Any]:
    default_spec = {
        "contract": str(node.get("input_contract") or node.get("input_type") or "custom"),
        "type": str(node.get("input_type") or node.get("input_contract") or "custom"),
        "size": node.get("input_size"),
        "align": node.get("input_align"),
    }
    node_type_name = str(node.get("type", ""))
    if node_type_name not in MULTI_INPUT_PORTS:
        return default_spec
    input_ports = node.get("input_ports")
    if port is None:
        return default_spec
    if not isinstance(input_ports, dict):
        input_ports = {}
    port_spec = input_ports.get(port)
    primary_port = str(node.get("primary_input_port") or "")
    if not isinstance(port_spec, dict):
        return default_spec if primary_port == port else {"contract": "custom", "type": "custom", "size": None, "align": None}
    spec = dict(default_spec)
    if port_spec.get("contract") not in (None, ""):
        spec["contract"] = str(port_spec.get("contract"))
    if port_spec.get("type") not in (None, ""):
        spec["type"] = str(port_spec.get("type"))
    if port_spec.get("size") not in (None, ""):
        spec["size"] = port_spec.get("size")
    if port_spec.get("align") not in (None, ""):
        spec["align"] = port_spec.get("align")
    return spec


def contract_name_for_output(node: dict[str, Any]) -> str:
    node_type_name = str(node.get("type", ""))
    if node_type_name == "processor.custom":
        return str(node.get("output_contract") or node.get("output_type") or "custom")
    if node_type_name == "algorithm.pid":
        return "efw_pid_output_t"
    if node_type_name == "algorithm.custom":
        return str(node.get("output_contract") or node.get("output_type") or node.get("io_contract") or "custom")
    if node_type_name == "event.subscriber":
        return str(node.get("output_contract") or node.get("payload_type") or node.get("topic") or "custom")
    if node_type_name == "sensor.line_tracking":
        return str(node.get("output_contract") or "efw_line_tracking_data_t")
    if node_type_name.startswith("sensor."):
        return str(node.get("output_contract") or node.get("output_type") or "custom")
    return str(node.get("output_contract") or node.get("output_type") or "custom")


def contract_name_for_input(node: dict[str, Any], port: str | None = None) -> str:
    node_type_name = str(node.get("type", ""))
    if node_type_name == "processor.custom":
        spec = node_input_spec(node, port)
        return str(spec.get("contract") or spec.get("type") or "custom")
    if node_type_name == "algorithm.pid":
        return "efw_pid_input_t"
    if node_type_name == "algorithm.custom":
        spec = node_input_spec(node, port)
        return str(spec.get("contract") or spec.get("type") or node.get("io_contract") or "custom")
    if node_type_name == "module.custom":
        spec = node_input_spec(node, port)
        return str(spec.get("contract") or spec.get("type") or node.get("input_contract") or node.get("input_type") or "custom")
    if node_type_name == "actuator.motor":
        return str(node.get("input_contract") or "efw_motor_cmd_t")
    if node_type_name == "actuator.custom":
        return str(node.get("input_contract") or node.get("input_type") or "custom")
    return str(node.get("input_contract") or node.get("input_type") or "custom")


def line_follower_node_ids(flows: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for flow in flows:
        if isinstance(flow, dict) and flow.get("type") == "control.line_follower":
            result.update(str(flow.get(key, "")) for key in ["sensor", "pid", "left_motor", "right_motor"] if flow.get(key))
    return result


def runtime_dataflow_paths(raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], raw_flows: list[dict[str, Any]], project: dict[str, Any]) -> list[list[str]]:
    runtime_types = {"sensor.custom", "sensor.line_tracking", "processor.custom", "algorithm.pid", "algorithm.custom", "actuator.motor", "actuator.custom", "module.custom"}
    flow_owned = line_follower_node_ids(raw_flows)
    include_flow_owned = bool(project.get("auto_dataflow_include_line_follower", False))
    adjacency: dict[str, list[str]] = {}
    for edge in raw_edges:
        if edge.get("kind", "generic") not in {"data_flow", "control_flow"}:
            continue
        src = nodes_by_id.get(edge.get("from"))
        dst = nodes_by_id.get(edge.get("to"))
        if not src or not dst:
            continue
        if src.get("type") not in runtime_types or dst.get("type") not in runtime_types:
            continue
        if not include_flow_owned and (src.get("id") in flow_owned or dst.get("id") in flow_owned):
            continue
        adjacency.setdefault(src["id"], []).append(dst["id"])
    starts = [node["id"] for node in raw_nodes if node.get("type") in {"sensor.custom", "sensor.line_tracking"} and node.get("id") in adjacency]
    paths: list[list[str]] = []

    def walk(node_id: str, path: list[str], seen: set[str]) -> None:
        next_ids = [item for item in adjacency.get(node_id, []) if item not in seen]
        if not next_ids:
            if len(path) > 1:
                paths.append(path[:])
            return
        for next_id in next_ids:
            walk(next_id, path + [next_id], seen | {next_id})

    for start in starts:
        walk(start, [start], {start})
    unique: list[list[str]] = []
    seen_keys: set[tuple[str, ...]] = set()
    for path in paths:
        key = tuple(path)
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(path)
    return unique


def validate_contract_fields(node: dict[str, Any]) -> None:
    contract = NODE_CONTRACTS[node["type"]]
    for field in contract.get("required", []):
        require(node.get(field) not in (None, "", []), f"{node['id']}.{field} is required by {node['type']} ({node_generation_label(node['type'])})")
    required_any = contract.get("required_any", [])
    if required_any:
        require(any(node.get(field) not in (None, "", []) for field in required_any), f"{node['id']} needs at least one of {', '.join(required_any)} by {node['type']} ({node_generation_label(node['type'])})")


def validate_contract_spec(owner: str, spec: dict[str, Any]) -> None:
    contract_name = str(spec.get("contract") or spec.get("type") or "custom")
    c_type = str(spec.get("type") or contract_name or "custom")
    size = spec.get("size")
    align = spec.get("align")
    require(isinstance(contract_name, str), f"{owner}.contract 必须是字符串")
    require(isinstance(c_type, str), f"{owner}.type 必须是字符串")
    if size not in (None, ""):
        require(int(size) >= 0, f"{owner}.size 必须 >= 0")
    if align not in (None, ""):
        require(int(align) > 0, f"{owner}.align 必须 > 0")
    builtin = BUILTIN_CONTRACTS.get(contract_name)
    if not builtin:
        return
    if c_type not in {"", "custom", str(builtin.get("c_type") or builtin.get("type") or contract_name)}:
        require(False, f"{owner} 与内建契约 {contract_name} 不一致：type 应为 {builtin.get('c_type')}")
    if size not in (None, "") and int(size) != int(builtin.get("size", 0) or 0):
        require(False, f"{owner} 与内建契约 {contract_name} 不一致：size 应为 {builtin.get('size')}")
    if align not in (None, "") and int(align) != int(builtin.get("align", 1) or 1):
        require(False, f"{owner} 与内建契约 {contract_name} 不一致：align 应为 {builtin.get('align')}")


def output_fields_for_contract(graph: dict[str, Any], contracts: dict[str, dict[str, Any]], contract_name: str) -> set[str]:
    c_type = resolve_contract_c_type(contracts, contract_name)
    builtin = BUILTIN_STRUCT_FIELDS.get(str(c_type))
    if builtin:
        return set(builtin)
    struct_node = next((item for item in graph.get("nodes", []) if item.get("type") == "data.struct" and item.get("name") == c_type), None)
    if not struct_node:
        return set()
    return {str(field.get("name", "")).strip() for field in struct_node.get("fields", []) if isinstance(field, dict) and str(field.get("name", "")).strip()}


def type_fields_for_contract(graph: dict[str, Any], contracts: dict[str, dict[str, Any]], contract_name: str) -> dict[str, str]:
    c_type = resolve_contract_c_type(contracts, contract_name)
    builtin = BUILTIN_STRUCT_FIELD_TYPES.get(str(c_type))
    if builtin:
        return dict(builtin)
    struct_node = next((item for item in graph.get("nodes", []) if item.get("type") == "data.struct" and item.get("name") == c_type), None)
    if not struct_node:
        return {}
    return {
        str(field.get("name", "")).strip(): str(field.get("type", "")).strip()
        for field in struct_node.get("fields", [])
        if isinstance(field, dict) and str(field.get("name", "")).strip()
    }


def resolve_nested_path_type(graph: dict[str, Any], root_type: str, path: str) -> str | None:
    current_type = str(root_type or "")
    if not path:
        return current_type or None
    segments = [segment.strip() for segment in str(path).split(".") if segment.strip()]
    if not segments:
        return current_type or None
    for segment in segments:
        builtin = BUILTIN_STRUCT_FIELD_TYPES.get(current_type)
        if builtin and segment in builtin:
            current_type = str(builtin[segment])
            continue
        struct_node = next((item for item in graph.get("nodes", []) if item.get("type") == "data.struct" and item.get("name") == current_type), None)
        if not struct_node:
            return None
        field = next((field for field in struct_node.get("fields", []) if isinstance(field, dict) and str(field.get("name", "")).strip() == segment), None)
        if not field:
            return None
        current_type = str(field.get("type", "")).strip()
    return current_type or None


def is_numeric_c_type(c_type: str) -> bool:
    return str(c_type) in {"float", "double", "int", "uint8_t", "uint16_t", "uint32_t", "int8_t", "int16_t", "int32_t"}


def validate_expr_text(owner: str, expr: str) -> None:
    text = str(expr or "").strip()
    require(text, f"{owner} expr 不能为空")
    require(re.fullmatch(r"[A-Za-z0-9_+\-*/%().<>=!&| \t]+", text) is not None, f"{owner} expr 只支持基础标识符/数字/运算符，不能包含分号、花括号或字符串")


def validate_processor_trigger_policy(node: dict[str, Any]) -> None:
    trigger_policy = str(node.get("trigger_policy") or "primary_only")
    allowed = set(TRIGGER_POLICY_CHOICES)
    require(trigger_policy in allowed, f"{node['id']}.trigger_policy 只支持 {', '.join(sorted(allowed))}")


def validate_processor_output_mode(node: dict[str, Any]) -> None:
    output_mode = str(node.get("output_mode") or "custom_code")
    allowed = set(OUTPUT_MODE_CHOICES)
    require(output_mode in allowed, f"{node['id']}.output_mode 只支持 {', '.join(sorted(allowed))}")
    if output_mode != "custom_code":
        require(str(node.get("output_contract") or "").strip(), f"{node['id']}.output_contract 不能为空")
        require(str(node.get("output_type") or "").strip(), f"{node['id']}.output_type 不能为空")


def validate_processor_mapping_mode(node: dict[str, Any]) -> None:
    mode = str(node.get("process_mode") or "full_custom")
    allowed = set(PROCESS_MODE_CHOICES)
    require(mode in allowed, f"{node['id']}.process_mode 只支持 {', '.join(sorted(allowed))}")
    process = str(node.get("process") or "").strip()
    if mode in {"full_custom", "mapping_then_custom"}:
        require(process and process == c_ident(process), f"{node['id']}.process 必须是有效的 C 标识符")
    if mode == "mapping_only":
        mappings = node.get("field_mappings", [])
        require(isinstance(mappings, list) and len(mappings) > 0, f"{node['id']}.field_mappings 不能为空，因为 process_mode=mapping_only")


def validate_field_mappings(node: dict[str, Any], graph: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> None:
    mappings = node.get("field_mappings", [])
    require(isinstance(mappings, list), f"{node['id']}.field_mappings 必须是数组")
    output_contract = str(node.get("output_contract") or node.get("output_type") or "custom")
    valid_fields = output_fields_for_contract(graph, contracts, output_contract)
    scalar_output = not valid_fields
    output_field_types = type_fields_for_contract(graph, contracts, output_contract)
    seen_fields: set[str] = set()
    allowed_sources = set(FIELD_MAPPING_SOURCE_CHOICES)
    allowed_transforms = set(FIELD_MAPPING_TRANSFORM_CHOICES)
    input_ports = node.get("input_ports", {}) if isinstance(node.get("input_ports"), dict) else {}
    primary_port = str(node.get("primary_input_port") or "")
    connected_ports = {str(edge.get("to_port", "")) for edge in graph.get("edges", []) if isinstance(edge, dict) and str(edge.get("to", "")) == str(node.get("id", ""))}
    for index, item in enumerate(mappings):
        require(isinstance(item, dict), f"{node['id']}.field_mappings[{index}] 必须是对象")
        field = str(item.get("field") or "").strip()
        source = str(item.get("source") or "").strip()
        transform = str(item.get("transform") or "identity").strip()
        if scalar_output:
            require(field in {"", "value"}, f"{node['id']}.field_mappings[{index}].field 在标量输出模式下只能为空或 value")
        else:
            require(field, f"{node['id']}.field_mappings[{index}].field 不能为空")
        require(field not in seen_fields, f"{node['id']}.field_mappings 中字段 {field} 重复")
        seen_fields.add(field)
        if valid_fields:
            require(field in valid_fields, f"{node['id']}.field_mappings[{index}].field={field} 不是输出类型 {output_contract} 的合法字段")
        require(source in allowed_sources, f"{node['id']}.field_mappings[{index}].source 不支持: {source}")
        require(transform in allowed_transforms, f"{node['id']}.field_mappings[{index}].transform 不支持: {transform}")
        target_type = output_field_types.get(field, resolve_contract_c_type(contracts, output_contract))
        if source == "const":
            require(item.get("value") not in (None, ""), f"{node['id']}.field_mappings[{index}] source=const 时必须填写 value")
        if source == "expr":
            validate_expr_text(f"{node['id']}.field_mappings[{index}]", str(item.get("expr") or ""))
        if source in {"sensor", "processor", "algorithm", "event", "module_input"}:
            require(source in input_ports or source == primary_port or source in connected_ports, f"{node['id']}.field_mappings[{index}] 引用了未声明输入端口 {source}")
            path = str(item.get("path") or "").strip()
            if path:
                port_contract = str(node_input_spec(node, source).get("contract") or node_input_spec(node, source).get("type") or "custom")
                port_root_type = resolve_contract_c_type(contracts, port_contract)
                require(resolve_nested_path_type(graph, port_root_type, path) is not None, f"{node['id']}.field_mappings[{index}].path={path} 不是输入 {source} 的合法字段路径")
        if transform in {"scale", "offset"}:
            require(is_numeric_c_type(target_type), f"{node['id']}.field_mappings[{index}] 使用 {transform} 时，目标字段 {field} 必须是数值类型")
        if transform == "to_uint16":
            require(str(target_type) == "uint16_t", f"{node['id']}.field_mappings[{index}] 使用 to_uint16 时，目标字段 {field} 必须是 uint16_t")
        if transform == "to_float":
            require(str(target_type) in {"float", "double"}, f"{node['id']}.field_mappings[{index}] 使用 to_float 时，目标字段 {field} 必须是 float/double")


def validate_algorithm_trigger_policy(node: dict[str, Any]) -> None:
    validate_processor_trigger_policy(node)


def validate_algorithm_output_mode(node: dict[str, Any]) -> None:
    validate_processor_output_mode(node)


def validate_algorithm_mapping_mode(node: dict[str, Any]) -> None:
    mode = str(node.get("process_mode") or "full_custom")
    allowed = set(PROCESS_MODE_CHOICES)
    require(mode in allowed, f"{node['id']}.process_mode 只支持 {', '.join(sorted(allowed))}")
    run = str(node.get("run") or "").strip()
    if mode in {"full_custom", "mapping_then_custom"}:
        require(run and run == c_ident(run), f"{node['id']}.run 必须是有效的 C 标识符")
    if mode == "mapping_only":
        mappings = node.get("field_mappings", [])
        require(isinstance(mappings, list) and len(mappings) > 0, f"{node['id']}.field_mappings 不能为空，因为 process_mode=mapping_only")


def validate_algorithm_field_mappings(node: dict[str, Any], graph: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> None:
    validate_field_mappings(node, graph, contracts)


def validate_module_trigger_policy(node: dict[str, Any]) -> None:
    validate_processor_trigger_policy(node)


def validate_module_output_mode(node: dict[str, Any]) -> None:
    validate_processor_output_mode(node)


def validate_module_mapping_mode(node: dict[str, Any]) -> None:
    mode = str(node.get("process_mode") or "full_custom")
    allowed = set(PROCESS_MODE_CHOICES)
    require(mode in allowed, f"{node['id']}.process_mode 只支持 {', '.join(sorted(allowed))}")
    poll = str(node.get("poll") or "").strip()
    if mode in {"full_custom", "mapping_then_custom"}:
        require(poll and poll == c_ident(poll), f"{node['id']}.poll 必须是有效的 C 标识符")
    if mode == "mapping_only":
        mappings = node.get("field_mappings", [])
        require(isinstance(mappings, list) and len(mappings) > 0, f"{node['id']}.field_mappings 不能为空，因为 process_mode=mapping_only")


def validate_module_field_mappings(node: dict[str, Any], graph: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> None:
    validate_field_mappings(node, graph, contracts)


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
    require(isinstance(items, list), f"{field_name} 必须是数组类型")
    result = []
    seen = set()
    for item in items:
        require(isinstance(item, dict), f"{field_name} 中的每一项必须是对象类型")
        rel_path = item.get("path")
        content = item.get("content", "")
        require(isinstance(rel_path, str) and rel_path, f"{field_name} 的 path 不能为空，请填写相对文件路径")
        require(isinstance(content, str), f"{field_name} 的 content 必须是字符串：{rel_path}")
        path = Path(rel_path)
        require(not path.is_absolute(), f"{field_name} 路径必须是相对路径：{rel_path}")
        require(".." not in path.parts, f"{field_name} 路径不能包含 '..'：{rel_path}")
        require(path.suffix in {".c", ".h", ".inc", ".md", ".txt"}, f"{field_name} 文件扩展名不支持：{rel_path}，仅支持 .c/.h/.inc/.md/.txt")
        normalized = path.as_posix()
        require(normalized not in GENERATED_FILES, f"{field_name} 不能覆盖自动生成的文件：{normalized}（请改用其他文件名）")
        require(normalized not in seen, f"{field_name} 路径重复：{normalized}")
        seen.add(normalized)
        if normalized.endswith(".c") and "efw_status_t" in content:
            has_include = '#include "efw/efw.h"' in content or "#include <efw/efw.h>" in content
            has_app_header = re.search(r'#include\s+"app_[A-Za-z0-9_./-]+\.h"', content) is not None
            require(has_include or has_app_header, f"{normalized} 使用了 EFW 符号但未包含 efw/efw.h 或 app_*.h 头文件，请添加 #include \"efw/efw.h\"")
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

    def module_poll_signature_key(node: dict[str, Any]) -> str:
        if str(node.get("type", "")) != "module.custom":
            return "module.lifecycle"
        input_ports = {str(edge.get("to_port", "")) for edge in ctx.get("edges", []) if isinstance(edge, dict) and str(edge.get("to", "")) == str(node.get("id", ""))}
        if input_ports & {"module_input", "event"}:
            return "module.poll"
        if isinstance(node.get("input_ports"), dict) and node.get("input_ports"):
            return "module.poll"
        return "module.lifecycle"

    def add(name: str | None, signature_key: str, owner: str) -> None:
        if not name:
            return
        params = CALLBACK_SIGNATURES[signature_key]
        normalized_params = normalize_c_params(params)
        cname = c_ident(name)
        require(name == cname, f"{owner} callback must be a valid C identifier: {name}")
        existing = callbacks.get(cname)
        require(not existing or existing["params"] == normalized_params, f"callback {cname} is declared with incompatible signatures")
        callbacks[cname] = {"params": normalized_params, "owner": owner, "return": CALLBACK_RETURNS.get(signature_key, "efw_status_t")}

    for node in ctx["nodes"]:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        for field, signature_key in contract.get("callbacks", {}).items():
            if signature_key in {"topic.callback", "condition"}:
                continue
            if str(node.get("type", "")) == "module.custom" and field == "poll":
                signature_key = module_poll_signature_key(node)
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
        apply_pair_semantics(src, dst, graph_view, c_ident_func=c_ident, overwrite=False, from_port=str(edge.get("from_port", "")), to_port=str(edge.get("to_port", "")))


def build_contract_registry(graph: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {
        name: {
            "name": name,
            "type": str(meta.get("type", name)),
            "c_type": str(meta.get("c_type", meta.get("type", name))),
            "size": int(meta.get("size", 0)),
            "align": int(meta.get("align", 1)),
            "producers": [],
            "consumers": [],
        }
        for name, meta in BUILTIN_CONTRACTS.items()
    }

    def add_contract(name: object, c_type: object = "custom", producer: object = "", consumer: object = "", size: object = None, align: object = None) -> None:
        if not name:
            return
        key = str(name)
        builtin = BUILTIN_CONTRACTS.get(key, {})
        resolved_type = str(c_type or builtin.get("type") or key or "custom")
        item = registry.setdefault(
            key,
            {
                "name": key,
                "type": resolved_type,
                "c_type": str(builtin.get("c_type") or resolved_type),
                "size": int(builtin.get("size", 0)),
                "align": int(builtin.get("align", 1)),
                "producers": [],
                "consumers": [],
            },
        )
        if c_type and str(c_type) != "custom" and item.get("type") in {"", "custom", key}:
            item["type"] = str(c_type)
            item["c_type"] = str(c_type)
        if size not in (None, ""):
            item["size"] = int(size)
        if align not in (None, ""):
            item["align"] = int(align)
        if producer and producer not in item["producers"]:
            item["producers"].append(producer)
        if consumer and consumer not in item["consumers"]:
            item["consumers"].append(consumer)

    for item in graph.get("contracts", []) or []:
        require(isinstance(item, dict), "contracts[] entries must be objects")
        add_contract(item.get("name"), item.get("c_type") or item.get("type", "custom"), item.get("producer", ""), item.get("consumer", ""), item.get("size"), item.get("align"))
    for node in nodes_by_id.values():
        node_type_name = node.get("type")
        if node_type_name == "processor.custom":
            seen_inputs: set[str] = set()
            for port_name in MULTI_INPUT_PORTS["processor.custom"]:
                spec = node_input_spec(node, port_name)
                contract_name = str(spec.get("contract") or spec.get("type") or "custom")
                if contract_name in seen_inputs:
                    continue
                seen_inputs.add(contract_name)
                add_contract(contract_name, spec.get("type", "custom"), consumer=f"{node.get('id')}:{port_name}", size=spec.get("size"), align=spec.get("align"))
            add_contract(node.get("output_contract"), node.get("output_type", "custom"), producer=node.get("id"), size=node.get("output_size"), align=node.get("output_align"))
        elif node_type_name == "algorithm.custom":
            seen_inputs: set[str] = set()
            for port_name in MULTI_INPUT_PORTS["algorithm.custom"]:
                spec = node_input_spec(node, port_name)
                contract_name = str(spec.get("contract") or spec.get("type") or "custom")
                if contract_name in seen_inputs:
                    continue
                seen_inputs.add(contract_name)
                add_contract(contract_name, spec.get("type", "custom"), consumer=f"{node.get('id')}:{port_name}", size=spec.get("size"), align=spec.get("align"))
            add_contract(contract_name_for_output(node), node.get("output_type") or contract_name_for_output(node), producer=node.get("id"), size=node.get("output_size"), align=node.get("output_align"))
        elif node_type_name == "module.custom":
            seen_inputs: set[str] = set()
            for port_name in MULTI_INPUT_PORTS["module.custom"]:
                spec = node_input_spec(node, port_name)
                contract_name = str(spec.get("contract") or spec.get("type") or "custom")
                if contract_name in seen_inputs:
                    continue
                seen_inputs.add(contract_name)
                add_contract(contract_name, spec.get("type", "custom"), consumer=f"{node.get('id')}:{port_name}", size=spec.get("size"), align=spec.get("align"))
            if node.get("output_type") or node.get("output_contract"):
                add_contract(contract_name_for_output(node), node.get("output_type") or contract_name_for_output(node), producer=node.get("id"), size=node.get("output_size"), align=node.get("output_align"))
        elif node_type_name == "sensor.line_tracking":
            add_contract(contract_name_for_output(node), "efw_line_tracking_data_t", producer=node.get("id"))
        elif node_type_name == "actuator.motor":
            add_contract(contract_name_for_input(node), "efw_motor_cmd_t", consumer=node.get("id"))
        elif node_type_name == "algorithm.pid":
            add_contract("efw_pid_input_t", "efw_pid_input_t", consumer=node.get("id"))
            add_contract("efw_pid_output_t", "efw_pid_output_t", producer=node.get("id"))
        elif node_type_name == "project.module":
            for name in node.get("inputs", []) or []:
                add_contract(name, "custom", consumer=node.get("id"))
            for name in node.get("outputs", []) or []:
                add_contract(name, "custom", producer=node.get("id"))
        elif node_type_name == "event.topic":
            add_contract(node.get("id"), node.get("payload_type", "custom"), producer=node.get("id"), consumer=node.get("id"))
        else:
            if node.get("output_contract") or node.get("output_type"):
                add_contract(contract_name_for_output(node), node.get("output_type") or contract_name_for_output(node), producer=node.get("id"), size=node.get("output_size"), align=node.get("output_align"))
            if node.get("input_contract") or node.get("input_type"):
                add_contract(contract_name_for_input(node), node.get("input_type") or contract_name_for_input(node), consumer=node.get("id"), size=node.get("input_size"), align=node.get("input_align"))
    return registry


def validate_runtime_dataflows(paths: list[list[str]], raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], contracts: dict[str, dict[str, Any]], project: dict[str, Any], tick_ms: int) -> None:
    edge_ports = {
        (str(edge.get("from", "")), str(edge.get("to", ""))): str(edge.get("to_port", ""))
        for edge in raw_edges
        if isinstance(edge, dict)
    }
    for path in paths:
        for node_id in path:
            period = int(nodes_by_id[node_id].get("period_ms", tick_ms))
            require(period > 0, f"{node_id}.period_ms must be > 0")
            require(period % tick_ms == 0, f"{node_id}.period_ms must be a multiple of project.tick_ms")
        for src_id, dst_id in zip(path, path[1:]):
            src = nodes_by_id[src_id]
            dst = nodes_by_id[dst_id]
            out_contract = contract_name_for_output(src)
            in_contract = contract_name_for_input(dst, edge_ports.get((src_id, dst_id)))
            require(out_contract == in_contract, f"dataflow contract mismatch: {src_id} outputs {out_contract}, but {dst_id} expects {in_contract}")
            if dst.get("type") == "algorithm.pid":
                require(in_contract == "efw_pid_input_t", f"{dst_id} is algorithm.pid and must receive efw_pid_input_t; add a processor.custom adapter before PID")
            if src.get("type") == "algorithm.pid":
                require(out_contract == "efw_pid_output_t", f"{src_id} is algorithm.pid and must output efw_pid_output_t")
            for contract_name in {out_contract, in_contract}:
                contract = resolve_contract(contracts, contract_name)
                require(contract is not None, f"dataflow references unknown contract: {contract_name}")
                require(resolve_contract_size(contracts, contract_name) > 0, f"contract {contract_name} needs size for automatic dataflow; add contracts[].size or node input/output_size")


def validate_event_contract_edges(raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], contracts: dict[str, dict[str, Any]]) -> None:
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        src = nodes_by_id.get(edge.get("from"))
        dst = nodes_by_id.get(edge.get("to"))
        if not src or not dst:
            continue
        src_type = str(src.get("type", ""))
        dst_type = str(dst.get("type", ""))
        from_port = str(edge.get("from_port", ""))
        to_port = str(edge.get("to_port", ""))
        if src_type == "event.subscriber" and dst_type in {"processor.custom", "algorithm.custom", "module.custom"}:
            out_contract = contract_name_for_output(src)
            in_contract = contract_name_for_input(dst, to_port)
            require(resolve_contract_c_type(contracts, out_contract) == resolve_contract_c_type(contracts, in_contract), f"event contract mismatch: {src.get('id')} outputs {out_contract}, but {dst.get('id')}({to_port}) expects {in_contract}")
        if dst_type == "event.publisher" and src_type in {"sensor.custom", "sensor.line_tracking", "processor.custom", "module.custom"} and from_port in {"sensor", "event_source", "processor", "module_output"}:
            topic = nodes_by_id.get(dst.get("topic"))
            if topic and topic.get("type") == "event.topic":
                out_contract = contract_name_for_output(src)
                topic_contract = str(topic.get("id"))
                require(resolve_contract_c_type(contracts, out_contract) == resolve_contract_c_type(contracts, topic_contract), f"publisher contract mismatch: {src.get('id')} outputs {out_contract}, but topic {topic.get('id')} expects payload {topic.get('payload_type')}")


def parse_event_trigger(value: str) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if ":" not in text:
        return None
    kind, payload = text.split(":", 1)
    kind = kind.strip()
    payload = payload.strip()
    if not kind or not payload:
        return None
    return kind, payload


def validate_event_trigger(node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    event_trigger = str(node.get("event_trigger", "")).strip()
    require(isinstance(node.get("event_trigger", ""), str), f"{node['id']}.event_trigger 必须是字符串")
    if not event_trigger:
        return
    parsed = parse_event_trigger(event_trigger)
    require(parsed is not None, f"{node['id']}.event_trigger 必须使用明确格式：topic:<event.topic节点id> 或 event:<事件名>")
    kind, payload = parsed
    if kind == "topic":
        require(payload in nodes_by_id and nodes_by_id[payload].get("type") == "event.topic", f"{node['id']}.event_trigger 使用 topic: 前缀时，必须引用存在的 event.topic 节点；当前值={event_trigger}")
        return
    if kind == "event":
        require(payload == c_ident(payload), f"{node['id']}.event_trigger 自定义事件名必须是有效的 C 标识符；当前值={event_trigger}")
        return
    require(False, f"{node['id']}.event_trigger 仅支持 topic: 或 event: 前缀；当前值={event_trigger}")


def validate_single_input_edges(raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    incoming_single_ports: dict[tuple[str, str], str] = {}
    for edge in raw_edges:
        dst_id = str(edge.get("to", ""))
        to_port = str(edge.get("to_port", ""))
        dst_node = nodes_by_id.get(dst_id)
        dst_type = str(dst_node.get("type", "")) if dst_node else ""
        if to_port not in SINGLE_INPUT_PORT_RULES.get(dst_type, set()):
            continue
        key = (dst_id, to_port)
        edge_id = str(edge.get("id", "edge"))
        existing_edge_id = incoming_single_ports.get(key)
        require(existing_edge_id is None, f"节点 {dst_id} 的输入端口 {to_port} 只允许一条来源连线；发现重复连线：{existing_edge_id} 和 {edge_id}。")
        incoming_single_ports[key] = edge_id


def resolve_contract(registry: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    return registry.get(str(name)) if name else None


def resolve_contract_c_type(registry: dict[str, dict[str, Any]], name: str) -> str:
    contract = resolve_contract(registry, name)
    return str(contract.get("c_type") or contract.get("type") or "custom") if contract else "custom"


def resolve_contract_size(registry: dict[str, dict[str, Any]], name: str) -> int:
    contract = resolve_contract(registry, name)
    return int(contract.get("size", 0) or 0) if contract else 0


def resolve_contract_align(registry: dict[str, dict[str, Any]], name: str) -> int:
    contract = resolve_contract(registry, name)
    return int(contract.get("align", 1) or 1) if contract else 1


def validate_node_fields_by_type(node: dict[str, Any], raw_nodes: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], graph: dict[str, Any] | None = None, contracts: dict[str, dict[str, Any]] | None = None) -> None:
    node_type_name = node["type"]
    if node_type_name == "hal.gpio_line_input":
        channels = int(node.get("channels", 0))
        require(channels > 0, f"{node['id']}.channels 必须大于 0，请设置循迹传感器的通道数")
        require(channels <= 8, f"{node['id']}.channels 不能超过默认最大值 EFW_LINE_TRACKING_MAX_CHANNELS=8")
        require(len(node.get("pins", [])) == channels, f"{node['id']}.pins 数组长度必须等于 channels={channels}，请补齐引脚定义")
        return
    if node_type_name == "sensor.line_tracking":
        require(node.get("input") in nodes_by_id, f"{node['id']}.input 必须引用一个 HAL 节点（如 hal.gpio_line_input）")
        require(node_type(nodes_by_id, node.get("input")) == "hal.gpio_line_input", f"{node['id']}.input 必须引用 hal.gpio_line_input 类型的节点")
        return
    if node_type_name == "actuator.motor":
        require(isinstance(node.get("pwm"), dict), f"{node['id']}.pwm 必须是对象类型，请设置 timer 和 channel 字段")
        require(isinstance(node.get("dir_pin"), dict), f"{node['id']}.dir_pin 必须是对象类型，请设置 port 和 pin 字段")
        return
    if node_type_name in {"actuator.custom", "sensor.custom"}:
        if node.get("hal_name"):
            require(node.get("hal_name") in nodes_by_id and nodes_by_id[node.get("hal_name")]["type"].startswith("hal."), f"{node['id']}.hal_name 必须引用一个 HAL 类型节点，当前引用 \"{node.get('hal_name')}\" 不存在或类型不对")
        return
    if node_type_name == "project.module":
        require(isinstance(node.get("display_name", node["id"]), str), f"{node['id']}.display_name 必须是字符串，用于在 UI 中显示模块名称")
        return
    if node_type_name == "event.topic":
        topic_id = int(node.get("topic_id", -1))
        require(0 <= topic_id <= 65535, f"{node['id']}.topic_id 必须在 0~65535 范围内，当前值={topic_id}")
        require(isinstance(node.get("payload_type", "void"), str), f"{node['id']}.payload_type 必须是字符串，如 \"float\" 或 \"uint16_t\"")
        return
    if node_type_name == "event.publisher":
        require(node.get("topic") in nodes_by_id and nodes_by_id[node.get("topic")]["type"] == "event.topic", f"{node['id']}.topic 必须引用一个 event.topic 节点，当前引用 \"{node.get('topic')}\" 不存在")
        if node.get("source"):
            require(node.get("source") in nodes_by_id, f"{node['id']}.source 引用了不存在的节点 \"{node.get('source')}\"，请检查数据来源节点是否存在")
        if node.get("data_expr"):
            require(isinstance(node.get("data_expr"), str) and node.get("data_expr"), f"{node['id']}.data_expr 必须是有效的 C 表达式字符串，如 \"&sensor_value\"")
        if node.get("size_expr"):
            require(isinstance(node.get("size_expr"), str) and node.get("size_expr"), f"{node['id']}.size_expr 必须是有效的 C 表达式字符串，如 \"sizeof(sensor_value)\"")
        return
    if node_type_name == "event.subscriber":
        require(node.get("topic") in nodes_by_id and nodes_by_id[node.get("topic")]["type"] == "event.topic", f"{node['id']}.topic 必须引用一个 event.topic 节点，当前引用 \"{node.get('topic')}\" 不存在")
        if node.get("target"):
            require(node.get("target") in nodes_by_id, f"{node['id']}.target 引用了不存在的节点 \"{node.get('target')}\"，请检查订阅目标节点是否存在")
        callback = node.get("callback")
        require(isinstance(callback, str) and callback == c_ident(callback), f"{node['id']}.callback 必须是有效的 C 标识符（仅字母数字下划线，不能以数字开头）")
        return
    if node_type_name == "state.machine":
        require(isinstance(node.get("initial", ""), str), f"{node['id']}.initial 必须是字符串，设为初始状态的 ID")
        machine_id = node.get("id")
        initial = node.get("initial", "")
        machine_states = [n for n in raw_nodes if n.get("type") == "state.state" and n.get("machine") == machine_id]
        if initial and machine_states:
            require(any(s.get("id") == initial for s in machine_states), f"{node['id']}.initial=\"{initial}\" 引用了不存在的状态，可用状态：{', '.join(s['id'] for s in machine_states)}")
        return
    if node_type_name == "state.state":
        require(node.get("machine") in nodes_by_id and nodes_by_id[node.get("machine")]["type"] == "state.machine", f"{node['id']}.machine 必须引用一个 state.machine 节点，当前引用 \"{node.get('machine')}\" 不存在")
        return
    if node_type_name == "state.transition":
        require(node.get("machine") in nodes_by_id and nodes_by_id[node.get("machine")]["type"] == "state.machine", f"{node['id']}.machine 必须引用一个 state.machine 节点，当前引用 \"{node.get('machine')}\" 不存在")
        require(node.get("from") in nodes_by_id and nodes_by_id[node.get("from")]["type"] == "state.state", f"{node['id']}.from 必须引用一个 state.state 节点（转换起点状态），当前引用 \"{node.get('from')}\" 不存在")
        require(node.get("to") in nodes_by_id and nodes_by_id[node.get("to")]["type"] == "state.state", f"{node['id']}.to 必须引用一个 state.state 节点（转换目标状态），当前引用 \"{node.get('to')}\" 不存在")
        require(nodes_by_id[node.get("from")].get("machine") == node.get("machine") and nodes_by_id[node.get("to")].get("machine") == node.get("machine"), f"{node['id']} 的起点和终点状态必须属于同一个 state.machine \"{node.get('machine')}\"")
        condition = str(node.get("condition", "")).strip()
        require(condition, f"{node['id']}.condition 不能为空，请填写 C 条件函数名（如 check_timeout）")
        require(condition == c_ident(condition), f"{node['id']}.condition 必须是有效的 C 标识符")
        if node.get("action"):
            require(node.get("action") == c_ident(node.get("action")), f"{node['id']}.action 必须是有效的 C 标识符")
        require(int(node.get("priority", 0)) >= 0, f"{node['id']}.priority 必须 >= 0")
        require(int(node.get("timeout_ms", 0)) >= 0, f"{node['id']}.timeout_ms 必须 >= 0")
        validate_event_trigger(node, nodes_by_id)
        return
    if node_type_name == "processor.custom":
        process = str(node.get("process") or "")
        if process:
            require(process == c_ident(process), f"{node['id']}.process 必须是有效的 C 标识符（处理函数名）")
        require(isinstance(node.get("input_contract", "custom"), str), f"{node['id']}.input_contract 必须是字符串，指定输入数据契约名称")
        require(isinstance(node.get("output_contract", "custom"), str), f"{node['id']}.output_contract 必须是字符串，指定输出数据契约名称")
        validate_contract_spec(f"{node['id']}.input", node_input_spec(node))
        input_ports = node.get("input_ports")
        if input_ports not in (None, ""):
            require(isinstance(input_ports, dict), f"{node['id']}.input_ports 必须是对象，按端口描述输入契约")
            for port_name, port_spec in input_ports.items():
                require(port_name in MULTI_INPUT_PORTS["processor.custom"], f"{node['id']}.input_ports 包含未知端口 {port_name}，只支持 {', '.join(MULTI_INPUT_PORTS['processor.custom'])}")
                require(isinstance(port_spec, dict), f"{node['id']}.input_ports.{port_name} 必须是对象")
                validate_contract_spec(f"{node['id']}.input_ports.{port_name}", node_input_spec(node, port_name))
        primary_input_port = str(node.get("primary_input_port") or "")
        if primary_input_port:
            require(primary_input_port in MULTI_INPUT_PORTS["processor.custom"], f"{node['id']}.primary_input_port 只支持 {', '.join(MULTI_INPUT_PORTS['processor.custom'])}")
        validate_contract_spec(f"{node['id']}.output", {"contract": node.get("output_contract") or node.get("output_type"), "type": node.get("output_type") or node.get("output_contract"), "size": node.get("output_size"), "align": node.get("output_align")})
        require(graph is not None and contracts is not None, "internal: graph/contracts missing for processor.custom validation")
        validate_processor_trigger_policy(node)
        validate_processor_output_mode(node)
        validate_processor_mapping_mode(node)
        validate_field_mappings(node, graph, contracts)
        return
    if node_type_name == "algorithm.custom":
        input_ports = node.get("input_ports")
        if input_ports not in (None, ""):
            require(isinstance(input_ports, dict), f"{node['id']}.input_ports 必须是对象，按端口描述输入契约")
            for port_name, port_spec in input_ports.items():
                require(port_name in MULTI_INPUT_PORTS["algorithm.custom"], f"{node['id']}.input_ports 包含未知端口 {port_name}，只支持 {', '.join(MULTI_INPUT_PORTS['algorithm.custom'])}")
                require(isinstance(port_spec, dict), f"{node['id']}.input_ports.{port_name} 必须是对象")
                validate_contract_spec(f"{node['id']}.input_ports.{port_name}", node_input_spec(node, port_name))
        primary_input_port = str(node.get("primary_input_port") or "")
        if primary_input_port:
            require(primary_input_port in MULTI_INPUT_PORTS["algorithm.custom"], f"{node['id']}.primary_input_port 只支持 {', '.join(MULTI_INPUT_PORTS['algorithm.custom'])}")
        validate_contract_spec(f"{node['id']}.output", {"contract": node.get("output_contract") or node.get("output_type"), "type": node.get("output_type") or node.get("output_contract"), "size": node.get("output_size"), "align": node.get("output_align")})
        require(graph is not None and contracts is not None, "internal: graph/contracts missing for algorithm.custom validation")
        validate_algorithm_trigger_policy(node)
        validate_algorithm_output_mode(node)
        validate_algorithm_mapping_mode(node)
        validate_algorithm_field_mappings(node, graph, contracts)
        return
    if node_type_name == "module.custom":
        input_ports = node.get("input_ports")
        if input_ports not in (None, ""):
            require(isinstance(input_ports, dict), f"{node['id']}.input_ports 必须是对象，按端口描述输入契约")
            for port_name, port_spec in input_ports.items():
                require(port_name in MULTI_INPUT_PORTS["module.custom"], f"{node['id']}.input_ports 包含未知端口 {port_name}，只支持 {', '.join(MULTI_INPUT_PORTS['module.custom'])}")
                require(isinstance(port_spec, dict), f"{node['id']}.input_ports.{port_name} 必须是对象")
                validate_contract_spec(f"{node['id']}.input_ports.{port_name}", node_input_spec(node, port_name))
        primary_input_port = str(node.get("primary_input_port") or "")
        if primary_input_port:
            require(primary_input_port in MULTI_INPUT_PORTS["module.custom"], f"{node['id']}.primary_input_port 只支持 {', '.join(MULTI_INPUT_PORTS['module.custom'])}")
        if node.get("output_contract") or node.get("output_type"):
            validate_contract_spec(f"{node['id']}.output", {"contract": node.get("output_contract") or node.get("output_type"), "type": node.get("output_type") or node.get("output_contract"), "size": node.get("output_size"), "align": node.get("output_align")})
        require(graph is not None and contracts is not None, "internal: graph/contracts missing for module.custom validation")
        validate_module_trigger_policy(node)
        validate_module_output_mode(node)
        validate_module_mapping_mode(node)
        validate_module_field_mappings(node, graph, contracts)


def validate_module_references(raw_nodes: list[dict[str, Any]], module_ids: set[str], contracts: dict[str, dict[str, Any]]) -> None:
    for node in raw_nodes:
        if node.get("module"):
            require(node.get("module") in module_ids, f"{node['id']}.module 引用了不存在的模块 \"{node.get('module')}\"，请先创建对应的 project.module")
        if node.get("type") == "project.module":
            require(isinstance(node.get("inputs", []), list), f"{node['id']}.inputs 必须是数组类型")
            require(isinstance(node.get("outputs", []), list), f"{node['id']}.outputs 必须是数组类型")
            for name in node.get("inputs", []) + node.get("outputs", []):
                require(str(name) in contracts, f"{node['id']} 引用了未知的数据契约 \"{name}\"，请在 contracts 中声明")


def validate_flows(raw_flows: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], tick_ms: int) -> list[dict[str, Any]]:
    flows = []
    flow_ids = set()
    for flow in raw_flows:
        require(isinstance(flow, dict), "每个 flow 必须是对象类型")
        require(flow.get("type") in SUPPORTED_FLOW_TYPES, f"不受支持的 flow 类型：{flow.get('type')}，可用类型：{', '.join(SUPPORTED_FLOW_TYPES)}")
        flow_id = flow.get("id")
        require(isinstance(flow_id, str) and flow_id, "每个 flow 必须有非空的 id")
        require(flow_id not in flow_ids, f"flow ID \"{flow_id}\" 重复")
        flow_ids.add(flow_id)
        sensor = nodes_by_id.get(flow.get("sensor"))
        pid = nodes_by_id.get(flow.get("pid"))
        left_motor = nodes_by_id.get(flow.get("left_motor"))
        right_motor = nodes_by_id.get(flow.get("right_motor"))
        require(sensor and sensor.get("type") == "sensor.line_tracking", f"{flow_id}.sensor 必须引用 sensor.line_tracking 类型节点")
        require(pid and pid.get("type") in {"algorithm.pid", "algorithm.custom"}, f"{flow_id}.pid 必须引用 algorithm.pid 或 algorithm.custom 类型节点")
        if pid and pid.get("type") == "algorithm.custom":
            require(pid.get("io_contract") == "efw_pid", f"{flow_id}.pid 是自定义算法，必须声明 io_contract=efw_pid（LineFollower 传入 efw_pid_input_t 并期望 efw_pid_output_t）")
        require(left_motor and left_motor.get("type") == "actuator.motor", f"{flow_id}.left_motor 必须引用 actuator.motor 类型节点")
        require(right_motor and right_motor.get("type") == "actuator.motor", f"{flow_id}.right_motor 必须引用 actuator.motor 类型节点")
        input_node = nodes_by_id[sensor["input"]]
        require(len(flow.get("weights", [])) == int(input_node["channels"]), f"{flow_id}.weights 数组长度必须等于传感器通道数 {int(input_node['channels'])}")
        require(float(flow.get("dt", 0.001)) > 0.0, f"{flow_id}.dt 必须大于 0")
        period_ms = int(flow.get("period_ms", tick_ms))
        require(period_ms > 0, f"{flow_id}.period_ms 必须大于 0")
        require(period_ms % tick_ms == 0, f"{flow_id}.period_ms 必须是 project.tick_ms={tick_ms} 的整数倍")
        flows.append(flow)
    return flows


def validate_tasks(raw_tasks: list[dict[str, Any]], raw_nodes: list[dict[str, Any]], flow_ids_known: set[str], tick_ms: int) -> list[dict[str, Any]]:
    tasks = []
    task_ids = set()
    for item in raw_tasks + [node for node in raw_nodes if node.get("type") == "task.periodic"]:
        require(isinstance(item, dict), "每个 task 必须是对象类型")
        require(item.get("type", "task.periodic") == "task.periodic", f"不受支持的 task 类型：{item.get('type')}，只支持 task.periodic")
        task_id = item.get("id")
        require(isinstance(task_id, str) and task_id, "每个 task 必须有非空的 id")
        require(task_id not in task_ids, f"task ID \"{task_id}\" 重复")
        task_ids.add(task_id)
        require(item.get("call") or item.get("flow"), f"task \"{task_id}\" 需要设置 call 或 flow 字段（指定要调度执行的函数或流程）")
        if item.get("flow"):
            require(item.get("flow") in flow_ids_known, f"task \"{task_id}\".flow 引用了不存在的 flow \"{item.get('flow')}\"，可用 flow：{', '.join(sorted(flow_ids_known)) if flow_ids_known else '(无)'}")
        task_period = int(item.get("period_ms", tick_ms))
        require(task_period > 0, f"task \"{task_id}\".period_ms 必须大于 0")
        require(task_period % tick_ms == 0, f"task \"{task_id}\".period_ms 必须是 project.tick_ms={tick_ms} 的整数倍")
        tasks.append(item)
    return tasks


def validate_graph_header(graph: dict[str, Any]) -> tuple[dict[str, Any], int, list[Any]]:
    require(isinstance(graph, dict), "Graph 根节点必须是对象（JSON object），不能是数组或基本类型")
    project = graph.get("project", {})
    require(isinstance(project, dict), "project 字段必须是对象类型，请添加 {\"name\": \"...\", \"tick_ms\": 1}")
    require(isinstance(project.get("name", "generated_app"), str), "project.name 必须是字符串，请设置项目名称")
    tick_ms = int(project.get("tick_ms", 1))
    require(tick_ms > 0, "project.tick_ms 必须大于 0，建议设为 1（1ms 周期）")
    contracts_decl = graph.get("contracts", [])
    require(isinstance(contracts_decl, list), "contracts 必须是数组类型，请使用 [] 语法")
    return project, tick_ms, contracts_decl


def validate_board_config(graph: dict[str, Any]) -> dict[str, Any]:
    board = graph.get("board", {})
    require(isinstance(board, dict), "board 必须是对象类型，请至少设置 {\"profile\": \"stm32-basic\"}")
    if "profile" in board:
        require(isinstance(board.get("profile"), str), "board.profile 必须是字符串，如 \"stm32-basic\" 或真实板卡 profile 名称")
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
    return board


def collect_raw_sections(graph: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    raw_nodes = graph.get("nodes")
    raw_flows = graph.get("flows", [])
    raw_tasks = graph.get("tasks", [])
    raw_edges = graph.get("edges", [])
    require(isinstance(raw_nodes, list) and raw_nodes, "nodes 不能为空数组，请至少添加一个节点（如 project.module）")
    require(isinstance(raw_flows, list), "flows 必须是数组类型，可以为空数组 []")
    require(isinstance(raw_tasks, list), "tasks 必须是数组类型，可以为空数组 []")
    require(isinstance(raw_edges, list), "edges 必须是数组类型，可以为空数组 []")
    return raw_nodes, raw_flows, raw_tasks, raw_edges


def build_nodes_by_id(raw_nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        require(isinstance(node, dict), "每个节点（node）必须是对象类型，请检查 nodes 数组中的元素格式")
        node_id = node.get("id")
        node_type_name = node.get("type")
        require(isinstance(node_id, str) and node_id, "每个节点必须有非空的 id 字段（字符串），请为节点设置唯一标识")
        require(node_type_name in SUPPORTED_NODE_TYPES, f"节点 {node_id} 的类型 \"{node_type_name}\" 不受支持，可用类型见模板面板")
        require(node_id not in nodes_by_id, f"节点 ID \"{node_id}\" 重复，请使用唯一的 id（可在属性面板中修改）")
        nodes_by_id[node_id] = node
    return nodes_by_id


def validate_edge_identity(raw_edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    edge_ids = set()
    for index, edge in enumerate(raw_edges):
        require(isinstance(edge, dict), f"edges[{index}] 必须是对象类型")
        edge_id = edge.get("id", f"edge_{index}")
        require(edge_id not in edge_ids, f"连线 ID \"{edge_id}\" 重复，请使用唯一的 id")
        edge_ids.add(edge_id)
        require(edge.get("from") in nodes_by_id, f"连线 {edge_id} 的 from 字段引用了不存在的节点 \"{edge.get('from')}\"，请检查连线起点")
        require(edge.get("to") in nodes_by_id, f"连线 {edge_id} 的 to 字段引用了不存在的节点 \"{edge.get('to')}\"，请检查连线终点")
        kind = edge.get("kind", "generic")
        require(kind in VALID_EDGE_KINDS, f"连线 {edge_id} 的 kind \"{kind}\" 不受支持，可用类型：{', '.join(sorted(VALID_EDGE_KINDS))}")


# Runtime node types that should be connected to be useful
RUNTIME_NODE_TYPES = {
    "sensor.custom", "sensor.line_tracking",
    "actuator.motor", "actuator.custom",
    "algorithm.pid", "algorithm.custom",
    "processor.custom", "module.custom",
}


def validate_orphan_nodes(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Warn about runtime nodes that have no data-flow connections."""
    connected_ids = set()
    for edge in edges:
        kind = edge.get("kind", "generic")
        if kind in {"data_flow", "control_flow", "hardware_dependency"}:
            connected_ids.add(edge.get("from"))
            connected_ids.add(edge.get("to"))
    warnings = []
    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type", "")
        if ntype in RUNTIME_NODE_TYPES and nid not in connected_ids:
            warnings.append(f"节点 \"{nid}\" ({ntype}) 没有数据流连线，可能生成死代码")
    return warnings


def validate_graph(graph: dict[str, Any], print_warnings: bool = False) -> dict[str, Any]:
    project, tick_ms, _contracts_decl = validate_graph_header(graph)
    board = validate_board_config(graph)
    raw_nodes, raw_flows, raw_tasks, raw_edges = collect_raw_sections(graph)
    nodes_by_id = build_nodes_by_id(raw_nodes)
    validate_edge_identity(raw_edges, nodes_by_id)
    validate_single_input_edges(raw_edges, nodes_by_id)
    apply_edge_semantics(raw_edges, nodes_by_id)

    # Warn about orphan runtime nodes
    orphan_warnings = validate_orphan_nodes(raw_nodes, raw_edges)
    if print_warnings and orphan_warnings:
        import sys
        for w in orphan_warnings:
            print(f"efw-codegen: 警告: {w}", file=sys.stderr)

    module_ids = {node["id"] for node in raw_nodes if node.get("type") == "project.module"}
    contracts = build_contract_registry(graph, nodes_by_id)
    for node in raw_nodes:
        validate_contract_fields(node)
        validate_node_fields_by_type(node, raw_nodes, nodes_by_id, graph, contracts)
    validate_module_references(raw_nodes, module_ids, contracts)
    validate_event_contract_edges(raw_edges, nodes_by_id, contracts)

    runtime_paths = runtime_dataflow_paths(raw_nodes, raw_edges, nodes_by_id, raw_flows, project)
    validate_runtime_dataflows(runtime_paths, raw_edges, nodes_by_id, contracts, project, tick_ms)

    flows = validate_flows(raw_flows, nodes_by_id, tick_ms)
    flow_ids_known = {flow["id"] for flow in flows}
    tasks = validate_tasks(raw_tasks, raw_nodes, flow_ids_known, tick_ms)

    custom_files, board_adapters = validate_custom_files(graph)
    ctx = {
        "project": project,
        "board": board,
        "nodes": raw_nodes,
        "nodes_by_id": nodes_by_id,
        "flows": flows,
        "tasks": tasks,
        "edges": raw_edges,
        "contracts": contracts,
        "runtime_dataflows": runtime_paths,
        "custom_files": custom_files,
        "board_adapters": board_adapters,
        "warnings": orphan_warnings,
    }
    validate_callback_implementations(ctx)
    return ctx
