"""Dataflow and trace rendering helpers for code generation."""

from __future__ import annotations

try:
    from .utils import c_ident, c_str
except ImportError:  # pragma: no cover - supports legacy top-level codegen imports
    from codegen.utils import c_ident, c_str


RUNTIME_DATAFLOW_TYPES = {
    "sensor.custom",
    "sensor.line_tracking",
    "processor.custom",
    "algorithm.pid",
    "algorithm.custom",
    "actuator.motor",
    "actuator.custom",
}


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
    """Return executable Sensor -> Processor/Algorithm -> Actuator paths."""
    if "runtime_dataflows" in ctx:
        return [list(path) for path in ctx.get("runtime_dataflows", [])]
    adjacency = {}
    for _edge, src, dst in dataflow_edges(ctx):
        if src.get("type") not in RUNTIME_DATAFLOW_TYPES or dst.get("type") not in RUNTIME_DATAFLOW_TYPES:
            continue
        adjacency.setdefault(src["id"], []).append(dst["id"])
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


def trace_begin(event: str, name: str) -> str:
    ident = c_ident(f"{event}_{name}_start")[:48]
    return f"    uint32_t trace_{ident}_ms = app_elapsed_ms();\n    efw_app_trace_event_ex({c_str(event)}, {c_str(name)}, EFW_OK, trace_{ident}_ms, EFW_APP_TRACE_DURATION_UNKNOWN);\n"


def trace_end(event: str, name: str, status_var: str = "s") -> str:
    begin_ident = c_ident(f"{event.replace('.end', '.begin')}_{name}_start")[:48]
    return f"    efw_app_trace_event_ex({c_str(event)}, {c_str(name)}, {status_var}, app_elapsed_ms(), app_elapsed_ms() - trace_{begin_ident}_ms);\n"


def trace_edge(edge_name: str, status_var: str = "s") -> str:
    return f"    efw_app_trace_event_ex(\"dataflow.edge\", {c_str(edge_name)}, {status_var}, app_elapsed_ms(), 0u);\n"
