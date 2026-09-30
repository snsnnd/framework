"""Debug and trace tools for EFW projects.

Shows the complete runtime flow of a generated EFW application:
- Initialization order
- Module registration sequence
- Dataflow pipelines
- Scheduler task timeline
- State machine transitions
- Event pub/sub topology
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from .validate import validate_graph
    from .generator import (
        build_runtime_summary,
        build_publisher_runtime_model,
        build_state_runtime_model,
        build_project_module_runtime_model,
        build_hal_runtime_model,
        build_sensor_runtime_model,
        build_actuator_runtime_model,
        dataflow_paths,
        dataflow_period_ms,
        nodes_of,
        event_topic_id,
    )
    from .utils import c_ident
except ImportError:  # pragma: no cover - supports legacy top-level codegen imports
    from codegen.validate import validate_graph
    from codegen.generator import (
        build_runtime_summary,
        build_publisher_runtime_model,
        build_state_runtime_model,
        build_project_module_runtime_model,
        build_hal_runtime_model,
        build_sensor_runtime_model,
        build_actuator_runtime_model,
        dataflow_paths,
        dataflow_period_ms,
        nodes_of,
        event_topic_id,
    )
    from codegen.utils import c_ident


# ─── Formatters ───────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"


def color(text: str, code: str) -> str:
    """Apply ANSI color if stdout is a TTY."""
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


def header(title: str) -> str:
    """Format a section header."""
    return f"\n{color('━' * 60, DIM)}\n{color(f'  {title}', BOLD + CYAN)}\n{color('━' * 60, DIM)}"


def item(label: str, detail: str = "", indent: int = 2) -> str:
    """Format a list item."""
    prefix = " " * indent
    if detail:
        return f"{prefix}{color('●', GREEN)} {label}{color(f'  ({detail}', DIM)}{color(')', DIM)}"
    return f"{prefix}{color('●', GREEN)} {label}"


def arrow(label: str, detail: str = "", indent: int = 2) -> str:
    """Format an arrow item in a flow."""
    prefix = " " * indent
    if detail:
        return f"{prefix}{color('→', YELLOW)} {label}{color(f'  [{detail}]', DIM)}"
    return f"{prefix}{color('→', YELLOW)} {label}"


def tag(text: str, color_code: str = CYAN) -> str:
    """Format a tag."""
    return color(f"[{text}]", color_code)


def node_type_icon(node_type: str) -> str:
    """Get icon for node type."""
    icons = {
        "hal.gpio_line_input": "🔌",
        "hal.custom": "🔧",
        "sensor.line_tracking": "📡",
        "sensor.custom": "📊",
        "actuator.motor": "⚙️",
        "actuator.custom": "🎛️",
        "algorithm.pid": "📐",
        "algorithm.custom": "🧮",
        "processor.custom": "🔄",
        "module.custom": "📦",
        "project.module": "📋",
        "event.topic": "📢",
        "event.publisher": "📤",
        "event.subscriber": "📥",
        "state.machine": "🔀",
        "state.state": "⭕",
        "state.transition": "➡️",
    }
    return icons.get(node_type, "•")


# ─── Analysis Functions ───────────────────────────────────────────────────────

def analyze_init_order(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze the initialization order of components."""
    order = []
    
    # HALs first
    for node in nodes_of(ctx, "hal.gpio_line_input") + nodes_of(ctx, "hal.custom"):
        order.append({
            "phase": "HAL Registration",
            "id": node["id"],
            "type": node.get("type"),
            "detail": f"bus_id={node.get('bus_id', 0)}",
        })
    
    # Sensors (depend on HAL)
    for node in nodes_of(ctx, "sensor.line_tracking") + nodes_of(ctx, "sensor.custom"):
        order.append({
            "phase": "Sensor Registration",
            "id": node["id"],
            "type": node.get("type"),
            "detail": f"hal={node.get('input', node.get('hal_name', 'none'))}",
        })
    
    # Actuators (depend on HAL)
    for node in nodes_of(ctx, "actuator.motor") + nodes_of(ctx, "actuator.custom"):
        order.append({
            "phase": "Actuator Registration",
            "id": node["id"],
            "type": node.get("type"),
            "detail": f"hal={node.get('hal_name', 'none')}",
        })
    
    # Algorithms
    for node in nodes_of(ctx, "algorithm.pid") + nodes_of(ctx, "algorithm.custom"):
        order.append({
            "phase": "Algorithm Registration",
            "id": node["id"],
            "type": node.get("type"),
            "detail": f"kp={node.get('kp', 'N/A')}",
        })
    
    # Custom modules
    for node in nodes_of(ctx, "module.custom"):
        order.append({
            "phase": "Module Registration",
            "id": node["id"],
            "type": node.get("type"),
            "detail": f"init={'✓' if node.get('init') else '✗'}, start={'✓' if node.get('start') else '✗'}",
        })
    
    # Project modules
    for node in nodes_of(ctx, "project.module"):
        order.append({
            "phase": "Project Module Registration",
            "id": node["id"],
            "type": "project.module",
            "detail": f"poll={'✓' if True else '✗'}",
        })
    
    # Event subscriptions
    for node in nodes_of(ctx, "event.subscriber"):
        topic = ctx["nodes_by_id"].get(node.get("topic"))
        order.append({
            "phase": "Event Subscription",
            "id": node["id"],
            "type": "event.subscriber",
            "detail": f"topic={topic['id'] if topic else 'none'}, callback={node.get('callback')}",
        })
    
    # State machine registration
    for machine in nodes_of(ctx, "state.machine"):
        states = [n for n in nodes_of(ctx, "state.state") if n.get("machine") == machine["id"]]
        order.append({
            "phase": "State Machine Registration",
            "id": machine["id"],
            "type": "state.machine",
            "detail": f"states={len(states)}, initial={machine.get('initial', 'first')}",
        })
    
    return order


def analyze_dataflows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze dataflow pipelines."""
    paths = dataflow_paths(ctx)
    flows = []
    
    for index, path in enumerate(paths, start=1):
        nodes = []
        for node_id in path:
            node = ctx["nodes_by_id"].get(node_id, {})
            nodes.append({
                "id": node_id,
                "type": node.get("type", "unknown"),
            })
        
        period = dataflow_period_ms(ctx, path)
        flows.append({
            "index": index,
            "nodes": nodes,
            "period_ms": period,
        })
    
    return flows


def analyze_scheduler(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze scheduler tasks."""
    tick_ms = int(ctx["project"].get("tick_ms", 1))
    tasks = []
    
    # Dataflow pipelines as implicit tasks
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        names = [ctx["nodes_by_id"].get(nid, {}).get("id", nid) for nid in path]
        period = dataflow_period_ms(ctx, path)
        tasks.append({
            "name": f"dataflow_{'_'.join(c_ident(n) for n in names[:4])}",
            "period_ms": period,
            "type": "dataflow",
            "detail": " → ".join(names),
        })
    
    # Explicit tasks
    for task in ctx.get("tasks", []):
        period = int(task.get("period_ms", tick_ms))
        tasks.append({
            "name": task.get("id", "unnamed"),
            "period_ms": period,
            "type": "task",
            "detail": f"call={task.get('call', 'N/A')}, flow={task.get('flow', 'N/A')}",
        })
    
    # Root state machines (ticked every cycle)
    for machine in nodes_of(ctx, "state.machine"):
        if not machine.get("module"):
            tasks.append({
                "name": f"sm_{machine['id']}",
                "period_ms": tick_ms,
                "type": "state_machine",
                "detail": "tick every cycle",
            })
    
    # Event processing
    if nodes_of(ctx, "event.topic"):
        tasks.append({
            "name": "event_queue_process",
            "period_ms": tick_ms,
            "type": "event",
            "detail": "deferred event dispatch",
        })
    
    # Module poll_all
    if nodes_of(ctx, "module.custom") or nodes_of(ctx, "project.module"):
        tasks.append({
            "name": "module_poll_all",
            "period_ms": tick_ms,
            "type": "module",
            "detail": "lifecycle poll",
        })
    
    return tasks


def analyze_state_machines(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze state machines."""
    machines = []
    
    for machine in nodes_of(ctx, "state.machine"):
        machine_id = machine["id"]
        states = [n for n in nodes_of(ctx, "state.state") if n.get("machine") == machine_id]
        transitions = [n for n in nodes_of(ctx, "state.transition") if n.get("machine") == machine_id]
        
        machine_info = {
            "id": machine_id,
            "initial": machine.get("initial", states[0]["id"] if states else "none"),
            "states": [],
            "transitions": [],
        }
        
        for state in states:
            machine_info["states"].append({
                "id": state["id"],
                "on_enter": state.get("on_enter", "none"),
                "on_update": state.get("on_update", "none"),
                "on_exit": state.get("on_exit", "none"),
            })
        
        for trans in sorted(transitions, key=lambda t: int(t.get("priority", 0))):
            from_state = ctx["nodes_by_id"].get(trans.get("from"), {})
            to_state = ctx["nodes_by_id"].get(trans.get("to"), {})
            machine_info["transitions"].append({
                "from": from_state.get("id", trans.get("from")),
                "to": to_state.get("id", trans.get("to")),
                "condition": trans.get("condition", "always"),
                "priority": trans.get("priority", 0),
                "timeout_ms": trans.get("timeout_ms", 0),
                "event_trigger": trans.get("event_trigger", ""),
            })
        
        machines.append(machine_info)
    
    return machines


def analyze_events(ctx: dict[str, Any]) -> dict[str, Any]:
    """Analyze event pub/sub topology."""
    topics = []
    publishers = []
    subscribers = []
    
    for node in nodes_of(ctx, "event.topic"):
        topics.append({
            "id": node["id"],
            "topic_id": node.get("topic_id", 0),
            "payload_type": node.get("payload_type", "void"),
        })
    
    for node in nodes_of(ctx, "event.publisher"):
        topic = ctx["nodes_by_id"].get(node.get("topic"))
        source = ctx["nodes_by_id"].get(node.get("source"))
        publishers.append({
            "id": node["id"],
            "topic": topic["id"] if topic else "none",
            "source": source["id"] if source else node.get("data_expr", "manual"),
            "interval_ms": node.get("interval_ms", 0),
        })
    
    for node in nodes_of(ctx, "event.subscriber"):
        topic = ctx["nodes_by_id"].get(node.get("topic"))
        subscribers.append({
            "id": node["id"],
            "topic": topic["id"] if topic else "none",
            "callback": node.get("callback", "none"),
        })
    
    return {
        "topics": topics,
        "publishers": publishers,
        "subscribers": subscribers,
    }


def analyze_line_followers(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze line follower flows."""
    flows = []
    for flow in ctx.get("flows", []):
        flows.append({
            "id": flow["id"],
            "sensor": flow.get("sensor"),
            "pid": flow.get("pid"),
            "left_motor": flow.get("left_motor"),
            "right_motor": flow.get("right_motor"),
            "base_speed": flow.get("base_speed", 65.0),
            "period_ms": flow.get("period_ms", ctx["project"].get("tick_ms", 1)),
        })
    return flows


# ─── Display Functions ────────────────────────────────────────────────────────

def display_project_info(ctx: dict[str, Any]) -> None:
    """Display project overview."""
    project = ctx.get("project", {})
    print(header("PROJECT INFO"))
    print(item("Name", project.get("name", "unnamed")))
    print(item("Tick", f"{project.get('tick_ms', 1)} ms"))
    print(item("Board", project.get("board_profile", "generic")))
    
    # Node statistics
    all_nodes = ctx.get("nodes", [])
    type_counts: dict[str, int] = {}
    for node in all_nodes:
        ntype = node.get("type", "unknown")
        type_counts[ntype] = type_counts.get(ntype, 0) + 1
    
    print(item("Total Nodes", str(len(all_nodes))))
    for ntype, count in sorted(type_counts.items()):
        print(item(f"  {node_type_icon(ntype)} {ntype}", str(count), indent=4))


def display_init_order(ctx: dict[str, Any]) -> None:
    """Display initialization order."""
    order = analyze_init_order(ctx)
    print(header("INITIALIZATION ORDER"))
    
    current_phase = ""
    for entry in order:
        if entry["phase"] != current_phase:
            current_phase = entry["phase"]
            print(f"\n  {color(current_phase, BOLD + MAGENTA)}")
        print(arrow(entry["id"], entry["detail"], indent=4))


def display_dataflows(ctx: dict[str, Any]) -> None:
    """Display dataflow pipelines."""
    flows = analyze_dataflows(ctx)
    if not flows:
        return
    
    print(header("DATAFLOW PIPELINES"))
    
    for flow in flows:
        idx = flow["index"]
        period = flow["period_ms"]
        print(f"\n  {color(f'Pipeline #{idx}', BOLD + YELLOW)}  {color(f'(period={period}ms)', DIM)}")
        
        for i, node in enumerate(flow["nodes"]):
            icon = node_type_icon(node["type"])
            prefix = "    " if i == 0 else "    " + "  " * (i - 1) + "  ↓ "
            print(f"{prefix}{icon} {color(node['id'], BOLD)} {color(node['type'], DIM)}")


def display_scheduler(ctx: dict[str, Any]) -> None:
    """Display scheduler timeline."""
    tasks = analyze_scheduler(ctx)
    if not tasks:
        return
    
    print(header("SCHEDULER TIMELINE"))
    
    # Group by period
    by_period: dict[int, list[dict]] = {}
    for task in tasks:
        period = task["period_ms"]
        by_period.setdefault(period, []).append(task)
    
    tick_ms = int(ctx["project"].get("tick_ms", 1))
    
    for period in sorted(by_period.keys()):
        period_tasks = by_period[period]
        label = f"{period}ms"
        if period == tick_ms:
            label += " (every tick)"
        print(f"\n  {color(label, BOLD + BLUE)}")
        
        for task in period_tasks:
            type_tag = tag(task["type"], YELLOW)
            print(f"    {color('●', GREEN)} {task['name']} {type_tag} {color(task['detail'], DIM)}")


def display_state_machines(ctx: dict[str, Any]) -> None:
    """Display state machines."""
    machines = analyze_state_machines(ctx)
    if not machines:
        return
    
    print(header("STATE MACHINES"))
    
    for machine in machines:
        machine_id = machine["id"]
        initial = machine["initial"]
        print(f"\n  {color(f'🔀 {machine_id}', BOLD + MAGENTA)}  {color(f'(initial={initial})', DIM)}")
        
        print(f"\n    {color('States:', BOLD)}")
        for state in machine["states"]:
            callbacks = []
            if state["on_enter"] != "none":
                callbacks.append(f"enter={state['on_enter']}")
            if state["on_update"] != "none":
                callbacks.append(f"update={state['on_update']}")
            if state["on_exit"] != "none":
                callbacks.append(f"exit={state['on_exit']}")
            detail = ", ".join(callbacks) if callbacks else "no callbacks"
            print(f"      {color('⭕', GREEN)} {state['id']} {color(detail, DIM)}")
        
        if machine["transitions"]:
            print(f"\n    {color('Transitions:', BOLD)}")
            for trans in machine["transitions"]:
                parts = []
                if trans["condition"] != "always":
                    parts.append(f"cond={trans['condition']}")
                if trans["timeout_ms"]:
                    parts.append(f"timeout={trans['timeout_ms']}ms")
                if trans["event_trigger"]:
                    parts.append(f"event={trans['event_trigger']}")
                parts.append(f"priority={trans['priority']}")
                detail = ", ".join(parts)
                print(f"      {color('→', YELLOW)} {trans['from']} → {trans['to']} {color(detail, DIM)}")


def display_events(ctx: dict[str, Any]) -> None:
    """Display event topology."""
    events = analyze_events(ctx)
    
    if not events["topics"] and not events["publishers"] and not events["subscribers"]:
        return
    
    print(header("EVENT SYSTEM"))
    
    if events["topics"]:
        print(f"\n  {color('Topics:', BOLD)}")
        for topic in events["topics"]:
            topic_id = topic["id"]
            payload = topic["payload_type"]
            topic_num = topic["topic_id"]
            print(f"    {color('📢', GREEN)} {topic_id} (id={topic_num}, payload={payload})")
    
    if events["publishers"]:
        print(f"\n  {color('Publishers:', BOLD)}")
        for pub in events["publishers"]:
            pub_id = pub["id"]
            topic = pub["topic"]
            interval = f"interval={pub['interval_ms']}ms" if pub["interval_ms"] else "manual"
            print(f"    {color('📤', YELLOW)} {pub_id} → topic:{topic} {color(f'[{interval}]', DIM)}")
    
    if events["subscribers"]:
        print(f"\n  {color('Subscribers:', BOLD)}")
        for sub in events["subscribers"]:
            sub_id = sub["id"]
            topic = sub["topic"]
            callback = sub["callback"]
            print(f"    {color('📥', CYAN)} {sub_id} ← topic:{topic} {color(f'callback={callback}', DIM)}")


def display_line_followers(ctx: dict[str, Any]) -> None:
    """Display line follower flows."""
    flows = analyze_line_followers(ctx)
    if not flows:
        return
    
    print(header("LINE FOLLOWER FLOWS"))
    
    for flow in flows:
        flow_id = flow["id"]
        speed = flow["base_speed"]
        period = flow["period_ms"]
        print(f"\n  {color(f'🏎️  {flow_id}', BOLD + GREEN)}  {color(f'(speed={speed}, period={period}ms)', DIM)}")
        print(f"    {color('→', YELLOW)} sensor: {flow['sensor']}")
        print(f"    {color('→', YELLOW)} pid: {flow['pid']}")
        print(f"    {color('→', YELLOW)} motors: {flow['left_motor']}, {flow['right_motor']}")


def display_runtime_loop(ctx: dict[str, Any]) -> None:
    """Display the 1ms runtime loop structure."""
    print(header("RUNTIME LOOP (1ms tick)"))
    
    print(f"\n  {color('app_loop_1ms() execution order:', BOLD)}")
    
    step = 1
    
    # Dataflow pipelines
    paths = dataflow_paths(ctx)
    if paths:
        print(f"\n    {color(f'{step}. Dataflow Pipelines', BOLD + YELLOW)}")
        for path in paths:
            names = [ctx["nodes_by_id"].get(nid, {}).get("id", nid) for nid in path]
            period = dataflow_period_ms(ctx, path)
            chain = " → ".join(names)
            print(f"       {color('→', YELLOW)} {chain} {color(f'(every {period}ms)', DIM)}")
        step += 1
    
    # Line follower flows
    flow_tasks = {task.get("flow") for task in ctx.get("tasks", []) if task.get("flow")}
    flows = [f for f in ctx.get("flows", []) if f["id"] not in flow_tasks]
    if flows:
        print(f"\n    {color(f'{step}. Line Follower Flows', BOLD + GREEN)}")
        for flow in flows:
            tick_ms = ctx['project'].get('tick_ms', 1)
            period = flow.get('period_ms', tick_ms)
            print(f"       {color('→', YELLOW)} {flow['id']} {color(f'(every {period}ms)', DIM)}")
        step += 1
    
    # Explicit tasks
    tasks = ctx.get("tasks", [])
    if tasks:
        print(f"\n    {color(f'{step}. Periodic Tasks', BOLD + BLUE)}")
        for task in tasks:
            period = task.get("period_ms", ctx["project"].get("tick_ms", 1))
            print(f"       {color('→', YELLOW)} {task.get('id', 'unnamed')} {color(f'(every {period}ms)', DIM)}")
        step += 1
    
    # Root auto-publishers
    publisher_model = build_publisher_runtime_model(ctx)
    root_publishers = [p for p in publisher_model if p["stage"] == "root app_update_1ms" and p["mode"] != "manual"]
    if root_publishers:
        print(f"\n    {color(f'{step}. Auto Publishers', BOLD + CYAN)}")
        for pub in root_publishers:
            topic_id = pub['topic_id']
            print(f"       {color('📤', YELLOW)} {pub['id']} → topic:{topic_id}")
        step += 1
    
    # Root state machines
    root_machines = [m for m in nodes_of(ctx, "state.machine") if not m.get("module")]
    if root_machines:
        print(f"\n    {color(f'{step}. State Machines', BOLD + MAGENTA)}")
        for machine in root_machines:
            print(f"       {color('🔀', MAGENTA)} {machine['id']}")
        step += 1
    
    # Event queue
    if nodes_of(ctx, "event.topic"):
        print(f"\n    {color(f'{step}. Event Queue Processing', BOLD + YELLOW)}")
        print(f"       {color('→', YELLOW)} process deferred events")
        step += 1
    
    # Module poll_all
    if nodes_of(ctx, "module.custom") or nodes_of(ctx, "project.module"):
        print(f"\n    {color(f'{step}. Module Poll All', BOLD + GREEN)}")
        modules = nodes_of(ctx, "module.custom") + nodes_of(ctx, "project.module")
        for mod in modules:
            print(f"       {color('📦', GREEN)} {mod['id']}")
        step += 1


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def debug_graph(graph_path: Path, sections: list[str] | None = None) -> int:
    """Analyze and display the runtime flow of an EFW graph."""
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        ctx = validate_graph(graph)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error loading graph: {exc}", file=sys.stderr)
        return 1
    
    all_sections = ["info", "init", "dataflow", "scheduler", "state", "events", "loop", "linefollower"]
    
    if sections is None or "all" in sections:
        sections = all_sections
    
    print(color(f"\n  EFW Runtime Flow Analysis: {graph_path.name}", BOLD))
    
    section_funcs = {
        "info": display_project_info,
        "init": display_init_order,
        "dataflow": display_dataflows,
        "scheduler": display_scheduler,
        "state": display_state_machines,
        "events": display_events,
        "loop": display_runtime_loop,
        "linefollower": display_line_followers,
    }
    
    for section in sections:
        func = section_funcs.get(section)
        if func:
            func(ctx)
    
    print(f"\n{color('━' * 60, DIM)}")
    print(color("  Analysis complete.", BOLD))
    print()
    
    return 0


def list_sections() -> None:
    """List available debug sections."""
    sections = [
        ("info", "Project overview and node statistics"),
        ("init", "Initialization and registration order"),
        ("dataflow", "Dataflow pipeline paths"),
        ("scheduler", "Scheduler task timeline"),
        ("state", "State machine definitions and transitions"),
        ("events", "Event pub/sub topology"),
        ("loop", "Runtime loop execution order"),
        ("linefollower", "Line follower flow configuration"),
        ("all", "Show all sections (default)"),
    ]
    print("\nAvailable debug sections:")
    for name, desc in sections:
        print(f"  {color(name, CYAN):<20} {desc}")
