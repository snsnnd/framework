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

try:
    from .utils import c_ident, macro_ident, c_str, c_float, c_bool, require, nodes_of, number_or_default
    from .validate import BUILTIN_CONTRACTS, contract_name_for_input, contract_name_for_output, resolve_contract_c_type, resolve_contract_size, validate_graph
    from .dataflow import dataflow_buffer_size, dataflow_edges, dataflow_paths, dataflow_period_ms, graph_edges_of, trace_begin, trace_edge, trace_end
    from .runtime_model import build_actuator_runtime_model, build_hal_runtime_model, build_project_module_runtime_model, build_publisher_runtime_model, build_runtime_summary, build_sensor_runtime_model, build_state_runtime_model, modules_of, publisher_event_trigger_match, publisher_payload_c_type, publisher_payload_size_expr, publisher_source_node, publishers_with_auto, source_auto_publishers, source_cache_c_type, state_machines_for_module
    from .state_render import render_project_module_registrations, render_project_module_shells, render_state_api_declarations, render_state_machine_bundle
    from .publisher_render import render_publisher_runtime
    from .platform_render import render_actuator_runtime_defs, render_hal_runtime_defs, render_platform_registrations, render_sensor_runtime_defs
except ImportError:  # pragma: no cover - supports legacy top-level codegen imports
    from codegen.utils import c_ident, macro_ident, c_str, c_float, c_bool, require, nodes_of, number_or_default
    from codegen.validate import BUILTIN_CONTRACTS, contract_name_for_input, contract_name_for_output, resolve_contract_c_type, resolve_contract_size, validate_graph
    from codegen.dataflow import dataflow_buffer_size, dataflow_edges, dataflow_paths, dataflow_period_ms, graph_edges_of, trace_begin, trace_edge, trace_end
    from codegen.runtime_model import build_actuator_runtime_model, build_hal_runtime_model, build_project_module_runtime_model, build_publisher_runtime_model, build_runtime_summary, build_sensor_runtime_model, build_state_runtime_model, modules_of, publisher_event_trigger_match, publisher_payload_c_type, publisher_payload_size_expr, publisher_source_node, publishers_with_auto, source_auto_publishers, source_cache_c_type, state_machines_for_module
    from codegen.state_render import render_project_module_registrations, render_project_module_shells, render_state_api_declarations, render_state_machine_bundle
    from codegen.publisher_render import render_publisher_runtime
    from codegen.platform_render import render_actuator_runtime_defs, render_hal_runtime_defs, render_platform_registrations, render_sensor_runtime_defs

def render_event_dispatch_fn(state_runtime):
    """Generate the dispatch callback used by efw_event_queue_process_ex."""
    parts = ["""static void app_dispatch_event_fn(const char *event_name, uint16_t topic_id,
                           const void *data, uint16_t size) {
"""]
    if state_runtime:
        parts.append("    efw_status_t s;\n")
    parts.append("""    g_app_event_name = event_name;
    g_app_event_topic_id = topic_id;
    g_app_event_data = data;
    g_app_event_size = size;
    if (topic_id != 0u) {
        efw_topic_publish(topic_id, data, size);
    }
""")
    for machine_runtime in state_runtime:
        ident = machine_runtime["ident"]
        parts.append(f"    s = app_sm_{ident}_dispatch_event(event_name, topic_id, data, size);\n")
        parts.append("    if (s == EFW_OK) return;\n")
    parts.append("}\n")
    return "".join(parts)


def render_event_queue_runtime(state_runtime):
    """Legacy wrapper: generates the dispatch fn for the events template."""
    return render_event_dispatch_fn(state_runtime)


def has_event_runtime(ctx):
    return bool(
        nodes_of(ctx, "event.topic")
        or nodes_of(ctx, "event.publisher")
        or nodes_of(ctx, "event.subscriber")
        or any(node.get("event_trigger") for node in nodes_of(ctx, "state.transition"))
    )


def render_event_runtime(ctx, state_runtime):
    if not has_event_runtime(ctx):
        return """efw_status_t app_post_event(const char *event_name, uint16_t topic_id,
                            const void *data, uint16_t size) {
    EFW_UNUSED(event_name);
    EFW_UNUSED(topic_id);
    EFW_UNUSED(data);
    EFW_UNUSED(size);
    return EFW_ERR_UNSUPPORTED;
}

efw_status_t app_process_event_queue(void) { return EFW_OK; }

"""
    return render_event_dispatch_fn(state_runtime) + """
efw_status_t app_post_event(const char *event_name, uint16_t topic_id,
                            const void *data, uint16_t size) {
    return efw_event_queue_post_named(topic_id, event_name, data, size);
}

efw_status_t app_process_event_queue(void) {
    return efw_event_queue_process_ex(app_dispatch_event_fn);
}

"""


def dataflow_fn_name(path, index):
    names = [c_ident(node_id) for node_id in path]
    fn = "app_dataflow_" + "_".join(names[:4])
    if len(names) > 4:
        fn += f"_{index}"
    return fn


def scheduler_task_model(ctx, state_runtime, publisher_model):
    tasks = []
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        tasks.append({
            "ident": f"dataflow_{index}_{c_ident(path[0])}_{c_ident(path[-1])}",
            "name": f"dataflow/{index}/{'->'.join(path)}",
            "period_ms": dataflow_period_ms(ctx, path),
            "call": f"{dataflow_fn_name(path, index)}()",
        })
    flow_tasks = {task.get("flow") for task in ctx["tasks"] if task.get("flow")}
    for flow in ctx["flows"]:
        if flow["id"] in flow_tasks:
            continue
        ident = c_ident(flow["id"])
        tasks.append({
            "ident": f"flow_{ident}",
            "name": f"flow/{flow['id']}",
            "period_ms": int(flow.get("period_ms", ctx["project"].get("tick_ms", 1))),
            "call": f"efw_line_follower_update(&g_{ident}, 0, 0)",
        })
    for task in ctx["tasks"]:
        call = ""
        if task.get("call"):
            call = f"{c_ident(task['call'])}()"
        elif task.get("flow"):
            call = f"efw_line_follower_update(&g_{c_ident(task['flow'])}, 0, 0)"
        tasks.append({
            "ident": f"task_{c_ident(task['id'])}",
            "name": f"task/{task['id']}",
            "period_ms": int(task.get("period_ms", ctx["project"].get("tick_ms", 1))),
            "call": call,
        })
    root_publishers = [item for item in publisher_model if item["stage"] == "root app_update_1ms" and item["mode"] != "manual"]
    root_machines = [item for item in state_runtime if not item["module"]]
    tail_calls = [f"app_publish_{item['ident']}_auto()" for item in root_publishers]
    tail_calls.extend(f"app_sm_{machine['ident']}_tick()" for machine in root_machines)
    if has_event_runtime(ctx):
        tail_calls.append("app_process_event_queue()")
    if nodes_of(ctx, "module.custom") or nodes_of(ctx, "project.module"):
        tail_calls.append("efw_module_poll_all()")
    if tail_calls:
        tasks.append({
            "ident": "tail",
            "name": "app/tail",
            "period_ms": int(ctx["project"].get("tick_ms", 1)),
            "calls": tail_calls,
        })
    return tasks


def render_scheduler_tasks(ctx, state_runtime, publisher_model):
    parts = ["/* Core scheduler tasks. Registration order is the same-release execution order. */\n"]
    for task in scheduler_task_model(ctx, state_runtime, publisher_model):
        ident = task["ident"]
        parts.append(f"static efw_status_t app_scheduler_{ident}(void *ctx) {{\n    efw_status_t s;\n    EFW_UNUSED(ctx);\n")
        calls = task.get("calls", [task.get("call")])
        for call in calls:
            parts.append(f"    s = {call};\n    if (s != EFW_OK) return s;\n")
        parts.append("    return EFW_OK;\n}\n")
        parts.append(f"static const efw_scheduler_task_def_t g_app_scheduler_{ident}_task = {{\n")
        parts.append(f"    .name = {c_str(task['name'])},\n    .period_ms = {task['period_ms']}u,\n    .fn = app_scheduler_{ident},\n    .ctx = 0,\n}};\n\n")
    return "".join(parts)


def render_scheduler_registrations(ctx, state_runtime, publisher_model):
    parts = []
    for task in scheduler_task_model(ctx, state_runtime, publisher_model):
        parts.append(f"    s = efw_scheduler_register(&g_app_scheduler_{task['ident']}_task);\n    if (s != EFW_OK) return s;\n")
    return "".join(parts)


def render_scheduler_runtime(ctx, state_runtime, publisher_model):
    del ctx, state_runtime, publisher_model
    return """
static efw_status_t app_update_1ms(void) {
    g_app_elapsed_ms += APP_PROJECT_TICK_MS;
    return efw_scheduler_tick(app_elapsed_ms());
}

"""


def pin_expr(pin):
    port = str(pin.get("port", "A")).upper()
    require(port in {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"}, f"unsupported GPIO port: {port}")
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
    board_profile = board.get("profile") or ctx["project"].get("board_profile") or "stm32-basic"
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
#define APP_GPIO_PORT_D 3u
#define APP_GPIO_PORT_E 4u
#define APP_GPIO_PORT_F 5u
#define APP_GPIO_PORT_G 6u
#define APP_GPIO_PORT_H 7u
#define APP_GPIO_PORT_I 8u
#define APP_GPIO_PORT_J 9u
#define APP_GPIO_PORT_K 10u
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
        ctx_symbol = node.get("ctx", "0")
        algo_type = node.get("algo_type", "EFW_ALGO_CUSTOM")
        parts.append(f"extern efw_status_t app_algorithm_{ident}_dispatch(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size);\n")
        parts.append(f"""static efw_algo_ops_t g_{ident}_algo = {{
    .name = {c_str(node['id'])},
    .type = {algo_type},
    .ctx = {ctx_symbol},
    .run = app_algorithm_{ident}_dispatch,
}};

""")
    return "".join(parts)


def render_custom_module_runtime_defs(ctx):
    parts = []
    for node in nodes_of(ctx, "module.custom"):
        ident = c_ident(node["id"])
        module_type = node.get("module_type", "EFW_MODULE_CUSTOM")
        callbacks = {}
        for cb in ["init", "start", "stop"]:
            name = node.get(cb)
            callbacks[cb] = c_ident(name) if name else "0"
            if name:
                parts.append(f"extern efw_status_t {c_ident(name)}(void *ctx);\n")
        poll = node.get("poll")
        if poll:
            if node.get("input_ports"):
                callbacks["poll"] = f"app_module_{ident}_poll_bridge"
                parts.append(f"extern efw_status_t app_module_{ident}_poll_bridge(void *ctx);\n")
            else:
                callbacks["poll"] = c_ident(poll)
                parts.append(f"extern efw_status_t {c_ident(poll)}(void *ctx);\n")
        else:
            callbacks["poll"] = "0"
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


def render_platform_type_helpers(line_inputs, line_sensors, motors):
    parts = []
    if line_inputs:
        parts.append("""typedef struct {
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

    efw_status_t s = app_board_read_line_input(input->pins, input->channel_count, out);
    if (s != EFW_OK) return s;
    if (actual) *actual = sizeof(efw_line_tracking_data_t);
    return EFW_OK;
}

""")
    if line_sensors:
        parts.append("""static efw_status_t line_sensor_read(void *ctx, void *out, uint16_t out_size) {
    if (out_size < sizeof(efw_line_tracking_data_t)) return EFW_ERR_INVALID;
    return efw_hal_read((const char *)ctx, out, sizeof(efw_line_tracking_data_t), 0);
}

""")
    if motors:
        parts.append("""typedef struct {
    app_pwm_channel_t pwm;
    app_gpio_pin_t dir_pin;
} app_motor_ctx_t;

static efw_status_t motor_write(void *ctx, const void *cmd, uint16_t cmd_size) {
    app_motor_ctx_t *motor = (app_motor_ctx_t *)ctx;
    const efw_motor_cmd_t *motor_cmd = (const efw_motor_cmd_t *)cmd;
    if (!motor || !motor_cmd || cmd_size < sizeof(efw_motor_cmd_t)) return EFW_ERR_INVALID;

    return app_board_write_motor(motor->pwm, motor->dir_pin, motor_cmd);
}

""")
    return "".join(parts)


def render_platform_externs(ctx):
    parts = []
    if nodes_of(ctx, "hal.gpio_line_input"):
        parts.append("extern efw_status_t app_board_read_line_input(const app_gpio_pin_t *pins, uint8_t count, efw_line_tracking_data_t *out);\n")
    if nodes_of(ctx, "actuator.motor"):
        parts.append("extern efw_status_t app_board_write_motor(app_pwm_channel_t pwm, app_gpio_pin_t dir_pin, const efw_motor_cmd_t *cmd);\n")
    for node in nodes_of(ctx, "hal.custom"):
        for cb, sig in [("init", "void *ctx"), ("read", "void *ctx, void *buf, uint16_t len, uint16_t *actual"), ("write", "void *ctx, const void *buf, uint16_t len, uint16_t *actual"), ("ioctl", "void *ctx, uint32_t cmd, void *arg")]:
            if node.get(cb):
                parts.append(f"extern efw_status_t {c_ident(node[cb])}({sig});\n")
    for node in nodes_of(ctx, "actuator.custom"):
        parts.append(f"extern efw_status_t {c_ident(node['write'])}(void *ctx, const void *cmd, uint16_t cmd_size);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
        if node.get("enable"):
            parts.append(f"extern efw_status_t {c_ident(node['enable'])}(void *ctx);\n")
        if node.get("disable"):
            parts.append(f"extern efw_status_t {c_ident(node['disable'])}(void *ctx);\n")
    for node in nodes_of(ctx, "sensor.custom"):
        parts.append(f"extern efw_status_t {c_ident(node['read'])}(void *ctx, void *out, uint16_t out_size);\n")
        if node.get("init"):
            parts.append(f"extern efw_status_t {c_ident(node['init'])}(void *ctx);\n")
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
        line_state_body.append(f"    if (app_name_eq(input_name, {c_str(node['id'])})) {{\n        (void)count;\n        return;\n    }}\n")
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
uint32_t app_elapsed_ms(void);
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
        if (node.get("data_expr") and node.get("size_expr")) or node.get("source"):
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
    if state_runtime:
        parts.append("static efw_status_t app_noop_status(void *ctx) { EFW_UNUSED(ctx); return EFW_OK; }\n")
        parts.append("static uint8_t app_bootstrap_name_eq(const char *a, const char *b) { if (!a || !b) return 0u; while (*a && *b) { if (*a != *b) return 0u; ++a; ++b; } return (*a == *b) ? 1u : 0u; }\n")
    if any(node.get("event_trigger") for node in nodes_of(ctx, "state.transition")):
        parts.append("static uint8_t app_bootstrap_event_matches(const char *trigger, const char *event_name, uint16_t topic_id) {\n")
        parts.append("    if (trigger && event_name && trigger[0] == 'e' && trigger[1] == 'v' && trigger[2] == 'e' && trigger[3] == 'n' && trigger[4] == 't' && trigger[5] == ':' && app_bootstrap_name_eq(trigger + 6, event_name)) return 1u;\n")
        for topic in nodes_of(ctx, "event.topic"):
            parts.append(f"    if (topic_id == {event_topic_id(ctx, topic['id'])}u && app_bootstrap_name_eq(trigger, {c_str(publisher_event_trigger_match(topic['id']))})) return 1u;\n")
        parts.append("    return 0u;\n}\n")
    return "".join(parts)


def contract_size_expr(ctx, contract_name):
    contract = ctx.get("contracts", {}).get(str(contract_name), {})
    c_type = str(contract.get("c_type") or contract.get("type") or "")
    if c_type and c_type != "custom":
        return f"(uint16_t)sizeof({c_type})"
    return f"{resolve_contract_size(ctx.get('contracts', {}), str(contract_name))}u"


def incoming_port(ctx, node_id, default, source_id=None):
    for edge in ctx.get("edges", []):
        if (
            edge.get("to") == node_id
            and (source_id is None or edge.get("from") == source_id)
            and edge.get("kind", "generic") in {"data_flow", "control_flow"}
        ):
            return str(edge.get("to_port") or default)
    return str(default)


def input_port_specs(ctx, node, default_port):
    raw_ports = node.get("input_ports") if isinstance(node.get("input_ports"), dict) else {}
    if raw_ports:
        items = list(raw_ports.items())
    else:
        port = str(node.get("primary_input_port") or default_port)
        items = [(port, {
            "contract": node.get("input_contract") or node.get("input_type") or "custom",
            "type": node.get("input_type") or node.get("input_contract") or "custom",
        })]
    result = []
    for port, spec in items:
        contract = str(spec.get("contract") or spec.get("type") or "custom")
        result.append({
            "port": str(port),
            "ident": c_ident(port),
            "contract": contract,
            "c_type": str(spec.get("type") or spec.get("contract") or "custom"),
            "size_expr": contract_size_expr(ctx, contract),
        })
    return result


def render_input_cache(ctx, node, kind, default_port, with_dirty=False):
    ident = c_ident(node["id"])
    prefix = f"g_{kind}_{ident}"
    parts = []
    for port in input_port_specs(ctx, node, default_port):
        base = f"{prefix}_{port['ident']}"
        parts.append(f"static app_dataflow_buffer_t {base}_input;\nstatic uint16_t {base}_size;\nstatic uint8_t {base}_valid;\n")
        if with_dirty:
            parts.append(f"static uint8_t {base}_dirty;\n")
    if with_dirty:
        parts.append(f"static const char *{prefix}_active_port;\n")
    parts.append(f"static efw_status_t app_cache_{kind}_{ident}_port(const char *port, const void *data, uint16_t size) {{\n")
    parts.append("    if (!port || !data || size == 0u || size > APP_DATAFLOW_BUFFER_SIZE) return EFW_ERR_INVALID;\n")
    for port in input_port_specs(ctx, node, default_port):
        base = f"{prefix}_{port['ident']}"
        parts.append(f"    if (app_bootstrap_name_eq(port, {c_str(port['port'])})) {{\n")
        parts.append(f"        if (size != {port['size_expr']}) return EFW_ERR_INVALID;\n")
        parts.append(f"        memcpy({base}_input.raw, data, size);\n        {base}_size = size;\n        {base}_valid = 1u;\n")
        if with_dirty:
            parts.append(f"        {base}_dirty = 1u;\n        {prefix}_active_port = {c_str(port['port'])};\n")
        parts.append("        return EFW_OK;\n    }\n")
    parts.append("    return EFW_ERR_NOT_FOUND;\n}\n")
    return "".join(parts)


def render_multi_input_setup(ctx, node, kind, default_port, active_expr):
    ident = c_ident(node["id"])
    prefix = f"g_{kind}_{ident}"
    ports = input_port_specs(ctx, node, default_port)
    parts = [f"    efw_app_input_view_t views[{len(ports)}] = {{\n"]
    for port in ports:
        base = f"{prefix}_{port['ident']}"
        parts.append(f"        {{ {c_str(port['port'])}, {c_str(port['contract'])}, {c_str(port['c_type'])}, {base}_input.raw, {base}_size, {port['size_expr']}, {base}_valid }},\n")
    parts.append("    };\n")
    parts.append(f"    efw_app_multi_input_t multi = {{ views, {len(ports)}u, {active_expr} }};\n")
    return "".join(parts)


def trigger_condition(node, active_expr, prefix, default_port):
    policy = str(node.get("trigger_policy") or "primary_only")
    primary = str(node.get("primary_input_port") or next(iter(node.get("input_ports", {})), default_port))
    if policy == "manual":
        return "0"
    if policy == "event_only":
        return f"app_bootstrap_name_eq({active_expr}, \"event\") && {prefix}_event_valid"
    if policy == "any_input":
        return "1"
    return f"app_bootstrap_name_eq({active_expr}, {c_str(primary)}) && {prefix}_{c_ident(primary)}_valid"


def render_mapping_body(ctx, node, input_name="in"):
    output_contract = contract_name_for_output(node)
    output_type = resolve_contract_c_type(ctx.get("contracts", {}), output_contract)
    parts = [f"    {output_type} *mapped = ({output_type} *)out;\n", "    const efw_app_input_view_t *src_view;\n"]
    parts.append("    if (!mapped) return EFW_ERR_INVALID;\n")
    for mapping in node.get("field_mappings", []):
        field = str(mapping.get("field") or "")
        target = f"mapped->{field}" if field and field != "value" else "*mapped"
        source = str(mapping.get("source") or "")
        transform = str(mapping.get("transform") or "identity")
        if source == "const":
            value = c_float(mapping.get("value", 0)) if output_type in {"float", "double"} or field else str(mapping.get("value", 0))
            parts.append(f"    {target} = {value};\n")
            continue
        if source == "expr":
            parts.append(f"    {target} = ({mapping.get('expr')});\n")
            continue
        spec = node.get("input_ports", {}).get(source, {})
        source_type = str(spec.get("type") or spec.get("contract") or node.get("input_type") or "uint8_t")
        path = str(mapping.get("path") or "")
        value = f"(*(const {source_type} *)src_view->data)"
        if path:
            value = f"((const {source_type} *)src_view->data)->{path}"
        if transform == "to_float":
            value = f"(float)({value})"
        elif transform == "to_uint16":
            value = f"(uint16_t)({value})"
        elif transform == "scale":
            value = f"({value}) * {c_float(mapping.get('value', 1))}"
        elif transform == "offset":
            value = f"({value}) + {c_float(mapping.get('value', 0))}"
        parts.append(f"    src_view = efw_app_multi_input_get({input_name}, {c_str(source)});\n")
        parts.append("    if (!src_view || !src_view->valid || !src_view->data) return EFW_ERR_NOT_READY;\n")
        parts.append(f"    {target} = {value};\n")
    parts.append("    return EFW_OK;\n")
    return "".join(parts)

def render_state_logic_blocks(ctx):
    parts = []
    state_runtime = build_state_runtime_model(ctx)
    has_cache_runtime = bool(nodes_of(ctx, "processor.custom") + nodes_of(ctx, "algorithm.custom") + [node for node in nodes_of(ctx, "module.custom") if node.get("input_ports")])
    has_target_runtime = any(node.get("target") for node in nodes_of(ctx, "event.subscriber"))
    if (has_cache_runtime or has_target_runtime) and not state_runtime:
        parts.append("static uint8_t app_bootstrap_name_eq(const char *a, const char *b) { if (!a || !b) return 0u; while (*a && *b) { if (*a != *b) return 0u; ++a; ++b; } return (*a == *b) ? 1u : 0u; }\n")
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
        ident = c_ident(node["id"])
        process = c_ident(node["process"]) if node.get("process") else ""
        mode = str(node.get("process_mode") or "full_custom")
        default_port = str(node.get("primary_input_port") or "sensor")
        if process:
            parts.append(f"extern efw_status_t {process}(void *ctx, const efw_app_multi_input_t *in, void *out);\n")
        parts.append(render_input_cache(ctx, node, "processor", default_port))
        if mode in {"mapping_only", "mapping_then_custom"}:
            parts.append(f"static efw_status_t app_processor_{ident}_apply_mapping(const efw_app_multi_input_t *in, void *out) {{\n")
            parts.append(render_mapping_body(ctx, node))
            parts.append("}\n")
        parts.append(f"static efw_status_t app_processor_{ident}_run_port(const char *port, const void *data, uint16_t size, void *out, uint16_t out_size, uint8_t *did_run) {{\n")
        parts.append("    efw_status_t s;\n    EFW_UNUSED(out_size);\n    if (did_run) *did_run = 0u;\n")
        parts.append(f"    s = app_cache_processor_{ident}_port(port, data, size);\n    if (s != EFW_OK) return s;\n")
        parts.append(render_multi_input_setup(ctx, node, "processor", default_port, "port"))
        parts.append(f"    if (!({trigger_condition(node, 'port', f'g_processor_{ident}', default_port)})) return EFW_OK;\n")
        parts.append("    if (did_run) *did_run = 1u;\n")
        if mode in {"mapping_only", "mapping_then_custom"}:
            parts.append(f"    s = app_processor_{ident}_apply_mapping(&multi, out);\n    if (s != EFW_OK) return s;\n")
        if mode != "mapping_only":
            parts.append(f"    return {process}({node.get('ctx', '0')}, &multi, out);\n")
        else:
            parts.append("    return EFW_OK;\n")
        parts.append("}\n\n")
    for node in nodes_of(ctx, "algorithm.custom"):
        ident = c_ident(node["id"])
        run = c_ident(node["run"]) if node.get("run") else ""
        mode = str(node.get("process_mode") or "full_custom")
        default_port = str(node.get("primary_input_port") or "processor")
        if run:
            parts.append(f"extern efw_status_t {run}(void *ctx, const efw_app_multi_input_t *in, void *out);\n")
        parts.append(render_input_cache(ctx, node, "algorithm", default_port))
        if mode in {"mapping_only", "mapping_then_custom"}:
            parts.append(f"static efw_status_t app_algorithm_{ident}_apply_mapping(const efw_app_multi_input_t *in, void *out) {{\n")
            parts.append(render_mapping_body(ctx, node))
            parts.append("}\n")
        parts.append(f"static efw_status_t app_algorithm_{ident}_run_port(void *ctx, const char *port, const void *data, uint16_t in_size, void *out, uint16_t out_size, uint8_t *did_run) {{\n")
        parts.append("    efw_status_t s;\n    EFW_UNUSED(out_size);\n    if (did_run) *did_run = 0u;\n")
        parts.append(f"    s = app_cache_algorithm_{ident}_port(port, data, in_size);\n    if (s != EFW_OK) return s;\n")
        parts.append(render_multi_input_setup(ctx, node, "algorithm", default_port, "port"))
        parts.append(f"    if (!({trigger_condition(node, 'port', f'g_algorithm_{ident}', default_port)})) return EFW_OK;\n")
        parts.append("    if (did_run) *did_run = 1u;\n")
        if mode in {"mapping_only", "mapping_then_custom"}:
            parts.append(f"    s = app_algorithm_{ident}_apply_mapping(&multi, out);\n    if (s != EFW_OK) return s;\n")
        if mode != "mapping_only":
            parts.append(f"    return {run}(ctx ? ctx : {node.get('ctx', '0')}, &multi, out);\n")
        else:
            parts.append("    EFW_UNUSED(ctx);\n    return EFW_OK;\n")
        parts.append("}\n")
        primary = str(node.get("primary_input_port") or default_port)
        parts.append(f"efw_status_t app_algorithm_{ident}_dispatch(void *ctx, const void *data, uint16_t in_size, void *out, uint16_t out_size) {{\n    return app_algorithm_{ident}_run_port(ctx, {c_str(primary)}, data, in_size, out, out_size, 0);\n}}\n\n")
    for node in nodes_of(ctx, "module.custom"):
        if not node.get("poll") or not node.get("input_ports"):
            continue
        ident = c_ident(node["id"])
        poll = c_ident(node["poll"])
        mode = str(node.get("process_mode") or "full_custom")
        port = str(node.get("primary_input_port") or next(iter(node.get("input_ports", {})), "module_input"))
        parts.append(f"extern efw_status_t {poll}(void *ctx, const efw_app_multi_input_t *in);\n")
        parts.append(render_input_cache(ctx, node, "module", port, with_dirty=True))
        if mode in {"mapping_only", "mapping_then_custom"}:
            parts.append(f"static efw_status_t app_module_{ident}_apply_mapping(const efw_app_multi_input_t *in, void *out) {{\n")
            parts.append(render_mapping_body(ctx, node))
            parts.append("}\n")
        parts.append(f"efw_status_t app_module_{ident}_poll_bridge(void *ctx) {{\n")
        parts.append(render_multi_input_setup(ctx, node, "module", port, f"g_module_{ident}_active_port"))
        prefix = f"g_module_{ident}"
        policy = str(node.get("trigger_policy") or "primary_only")
        if policy == "any_input":
            condition = " || ".join(f"{prefix}_{item['ident']}_dirty" for item in input_port_specs(ctx, node, port))
        elif policy == "event_only":
            condition = f"{prefix}_event_dirty"
        elif policy == "manual":
            condition = "0"
        else:
            primary = str(node.get("primary_input_port") or port)
            condition = f"{prefix}_{c_ident(primary)}_dirty"
        parts.append(f"    if (!({condition})) return EFW_OK;\n")
        for item in input_port_specs(ctx, node, port):
            parts.append(f"    {prefix}_{item['ident']}_dirty = 0u;\n")
        if mode in {"mapping_only", "mapping_then_custom"}:
            output_type = resolve_contract_c_type(ctx.get("contracts", {}), contract_name_for_output(node))
            parts.append(f"    {output_type} mapped_out;\n    efw_status_t s = app_module_{ident}_apply_mapping(&multi, &mapped_out);\n    if (s != EFW_OK) return s;\n")
            if source_auto_publishers(ctx, node["id"]):
                parts.append(f"    app_cache_source_{ident}(&mapped_out, {contract_size_expr(ctx, contract_name_for_output(node))});\n")
        if mode != "mapping_only":
            parts.append(f"    return {poll}(ctx ? ctx : {node.get('ctx', '0')}, &multi);\n")
        else:
            parts.append("    EFW_UNUSED(ctx);\n    return EFW_OK;\n")
        parts.append("}\n\n")
    for subscriber in nodes_of(ctx, "event.subscriber"):
        target = ctx.get("nodes_by_id", {}).get(subscriber.get("target"))
        if not target or target.get("type") not in {"processor.custom", "algorithm.custom", "module.custom"}:
            continue
        sub_ident = c_ident(subscriber["id"])
        target_ident = c_ident(target["id"])
        callback = c_ident(subscriber["callback"])
        expected = contract_size_expr(ctx, contract_name_for_input(target, "event"))
        parts.append(f"static void app_subscriber_{sub_ident}_proxy(uint16_t topic_id, const void *data, uint16_t size, void *user) {{\n")
        parts.append(f"    if (data && size == {expected}) {{\n")
        if target.get("type") == "processor.custom":
            parts.append("        app_dataflow_buffer_t out;\n")
            parts.append(f"        (void)app_processor_{target_ident}_run_port(\"event\", data, size, out.raw, {contract_size_expr(ctx, contract_name_for_output(target))}, 0);\n")
        elif target.get("type") == "algorithm.custom":
            parts.append("        app_dataflow_buffer_t out;\n")
            parts.append(f"        (void)app_algorithm_{target_ident}_run_port({target.get('ctx', '0')}, \"event\", data, size, out.raw, {contract_size_expr(ctx, contract_name_for_output(target))}, 0);\n")
        else:
            parts.append(f"        if (app_cache_module_{target_ident}_port(\"event\", data, size) == EFW_OK && {c_bool(target.get('poll_on_event', False))}) (void)app_module_{target_ident}_poll_bridge({target.get('ctx', '0')});\n")
        parts.append("    }\n")
        parts.append(f"    {callback}(topic_id, data, size, user);\n}}\n\n")
    return "".join(parts)

def render_dataflow_pipelines(ctx):
    parts = []
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        fn = dataflow_fn_name(path, index)
        parts.append(f"static efw_status_t {fn}(void) {{\n")
        parts.append("    efw_status_t s;\n")
        parts.append("    app_dataflow_buffer_t buf_a;\n")
        parts.append("    app_dataflow_buffer_t buf_b;\n")
        parts.append("    EFW_UNUSED(buf_b);\n")
        if any(ctx["nodes_by_id"][node_id].get("type") in {"processor.custom", "algorithm.custom"} for node_id in path):
            parts.append("    uint8_t did_run;\n")
        parts.append(trace_begin("dataflow.begin", "->".join(path)))
        current = "buf_a.raw"
        scratch = "buf_b.raw"
        first = ctx["nodes_by_id"][path[0]]
        parts.append(trace_begin("node.begin", first["id"]))
        first_size = contract_size_expr(ctx, contract_name_for_output(first))
        parts.append(f"    s = efw_sensor_read({c_str(first['id'])}, {current}, {first_size});\n")
        parts.append(trace_end("node.end", first["id"]))
        parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
        if source_auto_publishers(ctx, first["id"]):
            parts.append(f"    app_cache_source_{c_ident(first['id'])}({current}, {publisher_payload_size_expr(ctx, source_auto_publishers(ctx, first['id'])[0])});\n")
        prev_id = first["id"]
        for node_id in path[1:]:
            node = ctx["nodes_by_id"][node_id]
            node_type = node.get("type")
            edge_name = f"{prev_id}->{node['id']}"
            parts.append(trace_edge(edge_name, "EFW_OK"))
            parts.append(trace_begin("node.begin", node["id"]))
            if node_type == "processor.custom":
                port = incoming_port(ctx, node["id"], node.get("primary_input_port") or "sensor", prev_id)
                in_size = contract_size_expr(ctx, contract_name_for_input(node, port))
                out_size = contract_size_expr(ctx, contract_name_for_output(node))
                parts.append(f"    s = app_processor_{c_ident(node['id'])}_run_port({c_str(port)}, {current}, {in_size}, {scratch}, {out_size}, &did_run);\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
                parts.append("    if (!did_run) goto app_dataflow_done;\n")
                if source_auto_publishers(ctx, node["id"]):
                    parts.append(f"    app_cache_source_{c_ident(node['id'])}({scratch}, {publisher_payload_size_expr(ctx, source_auto_publishers(ctx, node['id'])[0])});\n")
                current, scratch = scratch, current
            elif node_type == "algorithm.custom":
                port = incoming_port(ctx, node["id"], node.get("primary_input_port") or "processor", prev_id)
                parts.append(f"    s = app_algorithm_{c_ident(node['id'])}_run_port({node.get('ctx', '0')}, {c_str(port)}, {current}, {contract_size_expr(ctx, contract_name_for_input(node, port))}, {scratch}, {contract_size_expr(ctx, contract_name_for_output(node))}, &did_run);\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
                parts.append("    if (!did_run) goto app_dataflow_done;\n")
                current, scratch = scratch, current
            elif node_type == "algorithm.pid":
                port = incoming_port(ctx, node["id"], node.get("primary_input_port") or "processor", prev_id)
                parts.append(f"    s = efw_algo_run({c_str(node['id'])}, {current}, {contract_size_expr(ctx, contract_name_for_input(node, port))}, {scratch}, {contract_size_expr(ctx, contract_name_for_output(node))});\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
                current, scratch = scratch, current
            elif node_type in {"actuator.motor", "actuator.custom"}:
                parts.append(f"    s = efw_actuator_write({c_str(node['id'])}, {current}, {contract_size_expr(ctx, contract_name_for_input(node))});\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
            elif node_type == "module.custom":
                port = incoming_port(ctx, node["id"], node.get("primary_input_port") or "module_input", prev_id)
                parts.append(f"    s = app_cache_module_{c_ident(node['id'])}_port({c_str(port)}, {current}, {contract_size_expr(ctx, contract_name_for_input(node, port))});\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    if (s != EFW_OK) goto app_dataflow_done;\n")
            else:
                parts.append("    s = EFW_ERR_UNSUPPORTED;\n")
                parts.append(trace_end("node.end", node["id"]))
                parts.append("    goto app_dataflow_done;\n")
            prev_id = node["id"]
        parts.append("    s = EFW_OK;\n")
        parts.append("app_dataflow_done:\n")
        parts.append(trace_end("dataflow.end", "->".join(path)))
        parts.append("    return s;\n")
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
        callback = f"app_subscriber_{c_ident(node['id'])}_proxy" if node.get("target") else c_ident(node["callback"])
        bind_lines.append(f"    s = efw_topic_subscribe({event_topic_id(ctx, node['topic'])}u, {callback}, {node.get('user', '0')});\n    if (s != EFW_OK) return s;\n")
    for machine_runtime in state_runtime:
        bind_lines.append(f"    s = app_{machine_runtime['ident']}_register();\n    if (s != EFW_OK) return s;\n")
    bind_lines.append(render_scheduler_registrations(ctx, state_runtime, publisher_model))
    bind_lines.append("    EFW_UNUSED(s);\n    return EFW_OK;\n}\n\n")
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
        "EVENT_RUNTIME": render_event_runtime(ctx, state_runtime),
        "SCHEDULER_TASKS": render_scheduler_tasks(ctx, state_runtime, publisher_model),
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
    board_source = "\n".join(item["content"] for item in ctx["custom_files"] + ctx["board_adapters"])
    has_board_init = re.search(r"\befw_status_t\s+app_board_init\s*\(\s*void\s*\)\s*\{", board_source) is not None
    if not has_board_init:
        try:
            try:
                from tools.target import resolve_target
            except ImportError:  # pragma: no cover - legacy top-level codegen import
                from target import resolve_target
            resolve_target(
                chip=str(ctx["project"].get("chip") or ""),
                board_profile=str(ctx.get("board", {}).get("profile") or ""),
            )
            has_board_init = True
        except (ImportError, ValueError):
            pass
    return {
        "BOARD_INIT_DECL": "\nextern efw_status_t app_board_init(void);" if has_board_init else "",
        "BOARD_INIT_CALL": "    if (app_board_init() != EFW_OK) return 1;\n" if has_board_init else "",
        "SETUP": setup,
    }


def render_main_c(ctx):
    return render_text_template("main.c.tpl", **main_template_values(ctx))


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
        "app_bootstrap.h": render_bootstrap_h(ctx),
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
