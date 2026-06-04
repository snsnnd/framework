"""Shared graph-edge semantics for UI connections and code generation."""

from __future__ import annotations

from typing import Any, Callable

PORT_RULES = {
    # Module/System layer: only public module interfaces and event relationships.
    "project.module": {"in": ["module_input"], "out": ["module_output"]},
    "event.topic": {"out": ["topic"]},
    "event.publisher": {"in": ["event_source", "topic"], "out": ["event"]},
    "event.subscriber": {"in": ["topic"], "out": ["event"]},

    # Module-internal layer: hardware dependencies, data processors, algorithms, actuators, scheduling, state, and code hooks.
    "hal.gpio_line_input": {"out": ["hal"]},
    "hal.custom": {"out": ["hal"]},
    "sensor.line_tracking": {"in": ["hal"], "out": ["sensor"]},
    "sensor.custom": {"in": ["hal"], "out": ["sensor", "event_source"]},
    "processor.custom": {"in": ["sensor", "algorithm", "event", "module_input"], "out": ["processor", "algorithm", "control", "module_output", "event_source"]},
    "algorithm.pid": {"in": ["sensor", "processor"], "out": ["algorithm"]},
    "algorithm.custom": {"in": ["sensor", "processor"], "out": ["algorithm"]},
    "actuator.motor": {"in": ["control", "motor_pair"], "out": ["motor_pair"]},
    "actuator.custom": {"in": ["hal", "control"]},
    "module.custom": {"in": ["module_input", "event", "schedule"], "out": ["module", "module_output", "event_source"]},
    "task.periodic": {"out": ["schedule"]},
    "state.machine": {"out": ["state_machine"]},
    "state.state": {"in": ["state_machine", "transition_to"], "out": ["transition_from"]},
    "state.transition": {"in": ["state_machine", "transition_from"], "out": ["transition_to"]},
    "data.enum": {"out": ["code"]},
    "data.struct": {"out": ["code"]},
    "custom.code": {"out": ["code"]},
}

PORT_COLORS = {
    "hal": "#26c6da",
    "sensor": "#66bb6a",
    "processor": "#29b6f6",
    "algorithm": "#ab47bc",
    "control": "#ec407a",
    "motor_pair": "#ff8a65",
    "module": "#ffb300",
    "module_input": "#b39ddb",
    "module_output": "#9575cd",
    "flow": "#42a5f5",
    "schedule": "#5c6bc0",
    "topic": "#ef5350",
    "event": "#ff7043",
    "event_source": "#ff8a65",
    "state_machine": "#00acc1",
    "transition_from": "#26a69a",
    "transition_to": "#80cbc4",
    "code": "#90a4ae",
}

PORT_LABELS = {
    "hal": "硬件接口",
    "sensor": "传感器数据",
    "processor": "处理后数据",
    "algorithm": "算法输出",
    "control": "控制命令",
    "motor_pair": "电机配对",
    "module": "模块调用",
    "module_input": "模块输入",
    "module_output": "模块输出",
    "flow": "调度 Flow",
    "schedule": "调度目标",
    "topic": "Topic",
    "event": "事件",
    "event_source": "事件源",
    "state_machine": "状态机",
    "transition_from": "状态转出",
    "transition_to": "状态转入",
    "code": "代码实现",
}

PORT_DESCRIPTIONS = {
    "hal": "硬件抽象层输出，可连接到 Sensor 或 Actuator。",
    "sensor": "模块内部数据流输出，可连接到 Processor、Algorithm 或 Event Publisher。",
    "processor": "processor.custom 的标准化输出，用于把原始数据转换为 PID/算法/执行器可消费的数据契约。",
    "algorithm": "算法输出，可连接到 Processor 或控制节点。",
    "control": "控制命令输入，常用于执行器。",
    "motor_pair": "电机配对端口，用于 LineFollower 等双电机控制 flow。",
    "module_input": "系统模块视图中的公共输入接口，只表达模块间数据契约。",
    "module_output": "系统模块视图中的公共输出接口，只表达模块间数据契约。",
    "topic": "事件总线 Topic，可连接 Publisher / Subscriber。",
    "event": "事件发布或订阅关系，可进入模块或 processor.custom。",
    "state_machine": "状态机容器端口，只能连接状态或转换。",
    "transition_from": "状态转换起点，只能从 State 连接到 Transition。",
    "transition_to": "状态转换终点，只能从 Transition 连接到 State。",
    "schedule": "调度线只表示 Task 周期调度哪个模块、flow 或用户回调。",
    "code": "自定义代码实现关系，回调名称仍在属性中声明。",
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
            ("sensor", "processor"),
            ("sensor", "event_source"),
            ("algorithm", "algorithm"),
            ("algorithm", "processor"),
            ("processor", "processor"),
            ("processor", "algorithm"),
            ("processor", "control"),
            ("processor", "module_input"),
            ("processor", "event_source"),
            ("motor_pair", "motor_pair"),
            ("control", "control"),
            ("schedule", "module"),
            ("module_output", "module_input"),
            ("module_output", "processor"),
            ("topic", "topic"),
            ("event_source", "event_source"),
            ("event", "event"),
            ("event", "processor"),
            ("state_machine", "state_machine"),
            ("state_machine", "transition_from"),
            ("transition_from", "transition_from"),
            ("transition_to", "transition_to"),
            ("flow", "schedule"),
            ("code", "hal"),
            ("code", "sensor"),
            ("code", "processor"),
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
        or (src_type == "project.module" and dst_type == "project.module")
        or (src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"})
        or (src_type in {"module.custom", "sensor.custom", "sensor.line_tracking", "processor.custom"} and dst_type == "event.publisher")
        or (src_type == "event.subscriber" and dst_type in {"module.custom", "processor.custom"})
        or (src_type == "state.machine" and dst_type in {"state.state", "state.transition"})
        or (src_type == "state.state" and dst_type == "state.transition")
        or (src_type == "state.transition" and dst_type == "state.state")
        or (src_type in {"sensor.custom", "sensor.line_tracking", "algorithm.pid", "algorithm.custom", "project.module", "event.subscriber"} and dst_type == "processor.custom")
        or (src_type == "processor.custom" and dst_type in {"algorithm.pid", "algorithm.custom", "actuator.motor", "actuator.custom", "project.module", "event.publisher"})
        or (src_type == "task.periodic" and dst_type == "module.custom")
        or (src_type == "sensor.line_tracking" and dst_type in {"algorithm.pid", "algorithm.custom"})
        or (src_type == "actuator.motor" and dst_type == "actuator.motor")
        or (src_type == "custom.code" and dst_type in {"sensor.custom", "processor.custom", "algorithm.custom", "module.custom", "actuator.custom", "hal.custom", "task.periodic"})
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
    if src_type == "project.module" and dst_type == "project.module":
        # Module-to-module edges describe public interface/data-flow at root level.
        # Submodule ownership is assigned by page ownership when adding cards, not by connecting modules.
        return True
    if src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"}:
        set_field(dst, "topic", src.get("id"))
        return True
    if src_type in {"module.custom", "sensor.custom", "sensor.line_tracking", "processor.custom"} and dst_type == "event.publisher":
        set_field(dst, "source", src.get("id"))
        return True
    if src_type == "event.subscriber" and dst_type in {"module.custom", "processor.custom"}:
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
    if src_type in {"sensor.custom", "sensor.line_tracking", "algorithm.pid", "algorithm.custom", "project.module", "event.subscriber"} and dst_type == "processor.custom":
        set_field(dst, "input_contract", src.get("output_type") or src.get("payload_type") or "custom")
        return True
    if src_type == "processor.custom" and dst_type in {"algorithm.pid", "algorithm.custom", "actuator.motor", "actuator.custom", "project.module", "event.publisher"}:
        if dst_type == "project.module":
            outputs = dst.setdefault("inputs", [])
            contract = src.get("output_contract") or src.get("output_type") or src.get("id")
            if isinstance(outputs, list) and contract not in outputs:
                outputs.append(contract)
        elif dst_type == "event.publisher":
            set_field(dst, "source", src.get("id"))
        elif dst_type == "algorithm.custom":
            set_field(dst, "input_type", src.get("output_contract") or src.get("output_type") or "custom")
        return True
    if src_type == "task.periodic" and dst_type == "module.custom":
        set_field(src, "call", dst.get("poll"))
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
    if src_type == "custom.code" and dst_type in {"sensor.custom", "processor.custom", "algorithm.custom", "module.custom", "actuator.custom", "hal.custom", "task.periodic"}:
        return True
    return False

EDGE_KIND_LABELS = {
    "contains": "归属关系",
    "data_flow": "数据流",
    "hardware_dependency": "硬件依赖",
    "schedule": "调度关系",
    "control_flow": "控制命令",
    "event": "事件关系",
    "state_transition": "状态转换",
    "state_transition_from": "状态转出",
    "state_transition_to": "状态转入",
    "code": "代码实现",
    "generic": "通用连接",
}

EDGE_EFFECT_DESCRIPTIONS = {
    "processor_to_module_input": "声明接口：把 processor 的 output_contract 追加到目标 project.module.inputs；不会调用模块。",
    "module_to_processor_input": "声明接口：把 project.module 的输出/公共契约作为 processor 输入；不会读取模块实现。",
    "event_to_processor": "事件订阅输出进入 processor；实际事件回调仍由 subscriber callback 承接。",
    "processor_to_event": "发布意图：把 processor 输出声明为 event.publisher.source；实际 publish 仍在用户代码中触发。",
    "runtime_dataflow": "运行管线：contract 名称、size 和 PID 输入/输出规则校验通过后，codegen 会按 Sensor → Processor/Algorithm → Actuator 生成周期执行链。",
    "hardware_dependency": "硬件依赖：写入 HAL 绑定字段或表达 HAL/COMM 到设备的依赖。",
    "schedule": "调度关系：Task 周期调度模块 poll、flow 或用户回调。",
    "event": "事件关系：写入 topic/source/target 字段；发布动作仍由用户代码决定。",
    "contains": "归属关系：只影响 Studio 页面/模块组织，不生成独立编译单元。",
}


def edge_effect_description(src: dict[str, Any], dst: dict[str, Any], from_port: str | None = None, to_port: str | None = None) -> str:
    src_type = str(src.get("type", ""))
    dst_type = str(dst.get("type", ""))
    if src_type == "processor.custom" and dst_type == "project.module":
        return EDGE_EFFECT_DESCRIPTIONS["processor_to_module_input"]
    if src_type == "project.module" and dst_type == "processor.custom":
        return EDGE_EFFECT_DESCRIPTIONS["module_to_processor_input"]
    if src_type == "event.subscriber" and dst_type == "processor.custom":
        return EDGE_EFFECT_DESCRIPTIONS["event_to_processor"]
    if src_type == "processor.custom" and dst_type == "event.publisher":
        return EDGE_EFFECT_DESCRIPTIONS["processor_to_event"]
    if src_type.startswith("sensor.") or dst_type.startswith(("processor.", "algorithm.", "actuator.")):
        if from_port in {"sensor", "processor", "algorithm", "control"} or to_port in {"sensor", "processor", "algorithm", "control"}:
            return EDGE_EFFECT_DESCRIPTIONS["runtime_dataflow"]
    kind = semantic_edge_kind(src, dst, from_port, to_port)
    return EDGE_EFFECT_DESCRIPTIONS.get(kind, "说明关系：保存为 graph.edges，供校验、文档和后续生成能力使用。")


def semantic_edge_kind(src: dict[str, Any], dst: dict[str, Any], from_port: str | None = None, to_port: str | None = None) -> str:
    """Return a normalized edge.kind instead of UI-only labels like selected/port."""
    src_type = str(src.get("type", ""))
    dst_type = str(dst.get("type", ""))
    if src_type == "project.module" and dst_type == "project.module":
        return "data_flow"
    if src_type == "project.module" and dst_type != "project.module":
        return "contains"
    if src_type.startswith("event.") or dst_type.startswith("event."):
        return "event"
    if from_port == "transition_from" and to_port == "transition_from":
        return "state_transition_from"
    if from_port == "transition_to" and to_port == "transition_to":
        return "state_transition_to"
    if src_type.startswith("state.") or dst_type.startswith("state."):
        return "state_transition"
    if from_port == "hal" or to_port == "hal":
        return "hardware_dependency"
    if src_type == "task.periodic" or from_port == "schedule" or to_port in {"schedule", "flow"}:
        return "schedule"
    if src_type == "custom.code":
        return "code"
    if from_port in {"module_output", "sensor", "processor", "algorithm", "control", "topic"} or to_port in {"module_input", "sensor", "processor", "algorithm", "control", "topic"}:
        return "data_flow"
    return "generic"
