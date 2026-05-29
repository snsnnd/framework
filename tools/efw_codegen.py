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
import shutil
import sys
from pathlib import Path

SUPPORTED_NODE_TYPES = {
    "hal.gpio_line_input",
    "sensor.line_tracking",
    "sensor.custom",
    "actuator.motor",
    "algorithm.pid",
    "algorithm.custom",
    "module.custom",
    "task.periodic",
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


def validate_custom_files(graph):
    custom_files = graph.get("custom_files", [])
    require(isinstance(custom_files, list), "custom_files must be an array when present")
    result = []
    seen = set()
    for item in custom_files:
        require(isinstance(item, dict), "each custom_files item must be an object")
        rel_path = item.get("path")
        content = item.get("content", "")
        require(isinstance(rel_path, str) and rel_path, "custom file path must be a non-empty string")
        require(isinstance(content, str), f"custom file content must be a string: {rel_path}")
        path = Path(rel_path)
        require(not path.is_absolute(), f"custom file path must be relative: {rel_path}")
        require(".." not in path.parts, f"custom file path must not contain '..': {rel_path}")
        normalized = path.as_posix()
        require(normalized not in GENERATED_FILES, f"custom file must not overwrite generated file: {normalized}")
        require(normalized not in seen, f"duplicate custom file path: {normalized}")
        seen.add(normalized)
        result.append({"path": normalized, "content": content})
    return result


def validate_graph(graph):
    require(isinstance(graph, dict), "graph root must be an object")
    project = graph.get("project", {})
    require(isinstance(project, dict), "project must be an object")
    require(isinstance(project.get("name", "generated_app"), str), "project.name must be a string")

    raw_nodes = graph.get("nodes")
    raw_flows = graph.get("flows", [])
    raw_tasks = graph.get("tasks", [])
    require(isinstance(raw_nodes, list) and raw_nodes, "nodes must be a non-empty array")
    require(isinstance(raw_flows, list), "flows must be an array")
    require(isinstance(raw_tasks, list), "tasks must be an array when present")

    nodes_by_id = {}
    for node in raw_nodes:
        require(isinstance(node, dict), "each node must be an object")
        node_id = node.get("id")
        node_type_name = node.get("type")
        require(isinstance(node_id, str) and node_id, "each node needs a non-empty string id")
        require(node_type_name in SUPPORTED_NODE_TYPES, f"unsupported node type for {node_id}: {node_type_name}")
        require(node_id not in nodes_by_id, f"duplicate node id: {node_id}")
        nodes_by_id[node_id] = node

    for node in raw_nodes:
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
        elif node_type_name == "sensor.custom":
            require(node.get("read"), f"{node['id']}.read must name a custom read callback")
        elif node_type_name == "algorithm.custom":
            require(node.get("run"), f"{node['id']}.run must name a custom run callback")

    flows = []
    for flow in raw_flows:
        require(isinstance(flow, dict), "each flow must be an object")
        require(flow.get("type") in SUPPORTED_FLOW_TYPES, f"unsupported flow type: {flow.get('type')}")
        flow_id = flow.get("id")
        require(isinstance(flow_id, str) and flow_id, "each flow needs a non-empty id")
        sensor = nodes_by_id.get(flow.get("sensor"))
        pid = nodes_by_id.get(flow.get("pid"))
        left_motor = nodes_by_id.get(flow.get("left_motor"))
        right_motor = nodes_by_id.get(flow.get("right_motor"))
        require(sensor and sensor.get("type") == "sensor.line_tracking", f"{flow_id}.sensor must reference sensor.line_tracking")
        require(pid and pid.get("type") in {"algorithm.pid", "algorithm.custom"}, f"{flow_id}.pid must reference algorithm.pid or algorithm.custom")
        require(left_motor and left_motor.get("type") == "actuator.motor", f"{flow_id}.left_motor must reference actuator.motor")
        require(right_motor and right_motor.get("type") == "actuator.motor", f"{flow_id}.right_motor must reference actuator.motor")
        input_node = nodes_by_id[sensor["input"]]
        require(len(flow.get("weights", [])) == int(input_node["channels"]), f"{flow_id}.weights length must match sensor channels")
        require(float(flow.get("dt", 0.001)) > 0.0, f"{flow_id}.dt must be > 0")
        require(int(flow.get("period_ms", 1)) > 0, f"{flow_id}.period_ms must be > 0")
        flows.append(flow)

    tasks = []
    for item in raw_tasks + [node for node in raw_nodes if node.get("type") == "task.periodic"]:
        require(isinstance(item, dict), "each task must be an object")
        require(item.get("type", "task.periodic") == "task.periodic", f"unsupported task type: {item.get('type')}")
        require(item.get("call") or item.get("flow"), f"task {item.get('id')} needs call or flow")
        require(int(item.get("period_ms", 1)) > 0, f"task {item.get('id')}.period_ms must be > 0")
        tasks.append(item)

    return {
        "project": project,
        "nodes": raw_nodes,
        "nodes_by_id": nodes_by_id,
        "flows": flows,
        "tasks": tasks,
        "custom_files": validate_custom_files(graph),
    }


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


def render_manifest(ctx):
    return f"""
/**
 * @file    app_manifest.h
 * @brief   Generated feature switches and registry capacities.
 */

#ifndef APP_MANIFEST_H
#define APP_MANIFEST_H

#include "app_board_config.h"

#define APP_USE_HAL                 {c_bool(len(nodes_of(ctx, 'hal.gpio_line_input')))}
#define APP_USE_SENSOR              {c_bool(len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom')))}
#define APP_USE_LINE_TRACKING       {c_bool(len(nodes_of(ctx, 'sensor.line_tracking')))}
#define APP_USE_ACTUATOR            {c_bool(len(nodes_of(ctx, 'actuator.motor')))}
#define APP_USE_MOTOR               {c_bool(len(nodes_of(ctx, 'actuator.motor')))}
#define APP_USE_ALGORITHM           {c_bool(len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom')))}
#define APP_USE_PID                 {c_bool(len(nodes_of(ctx, 'algorithm.pid')))}
#define APP_USE_MODULE              {c_bool(len(nodes_of(ctx, 'module.custom')))}

#define APP_HAL_COUNT               {len(nodes_of(ctx, 'hal.gpio_line_input'))}
#define APP_SENSOR_COUNT            {len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom'))}
#define APP_ACTUATOR_COUNT          {len(nodes_of(ctx, 'actuator.motor'))}
#define APP_ALGO_COUNT              {len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom'))}
#define APP_MODULE_COUNT            {len(nodes_of(ctx, 'module.custom'))}

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
    line_sensors = nodes_of(ctx, "sensor.line_tracking")
    custom_sensors = nodes_of(ctx, "sensor.custom")
    motors = nodes_of(ctx, "actuator.motor")
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

typedef struct {
    uint16_t channel[EFW_LINE_TRACKING_MAX_CHANNELS];
    uint8_t channel_count;
    const app_gpio_pin_t *pins;
} app_line_input_ctx_t;

typedef struct {
    app_pwm_channel_t pwm;
    app_gpio_pin_t dir_pin;
    float last_speed;
    float last_direction;
} app_motor_ctx_t;

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

static efw_status_t line_sensor_read(void *ctx, void *out) {
    return efw_hal_read((const char *)ctx, out, sizeof(efw_line_tracking_data_t), 0);
}

static efw_status_t motor_write(void *ctx, const void *cmd) {
    app_motor_ctx_t *motor = (app_motor_ctx_t *)ctx;
    const efw_motor_cmd_t *motor_cmd = (const efw_motor_cmd_t *)cmd;
    if (!motor || !motor_cmd) return EFW_ERR_INVALID;
    /* TODO(real board): speed -> PWM duty, direction -> GPIO level. */
    motor->last_speed = motor_cmd->speed;
    motor->last_direction = motor_cmd->direction;
    return EFW_OK;
}

"""]
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
    parts.append("efw_status_t app_platform_register(void) {\n    efw_status_t s;\n")
    for node in line_inputs:
        parts.append(f"    s = efw_hal_register(&g_{c_ident(node['id'])}_hal);\n    if (s != EFW_OK) return s;\n")
    for node in line_sensors + custom_sensors:
        parts.append(f"    s = efw_sensor_register(&g_{c_ident(node['id'])}_sensor);\n    if (s != EFW_OK) return s;\n")
    for node in motors:
        parts.append(f"    s = efw_actuator_register(&g_{c_ident(node['id'])}_motor);\n    if (s != EFW_OK) return s;\n")
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
efw_status_t app_loop_1ms(void);

#endif
"""


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

static uint32_t g_app_tick_ms;

"""]
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        weights = ", ".join(c_float(value) for value in flow["weights"])
        parts.append(f"static efw_line_follower_t g_{ident};\n")
        parts.append(f"static const float g_{ident}_weights[] = {{ {weights} }};\n")
    parts.append("\n")
    for task in ctx["tasks"]:
        if task.get("call"):
            parts.append(f"extern efw_status_t {c_ident(task['call'])}(void);\n")
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
    parts.append("    return EFW_OK;\n}\n\n")
    parts.append("static efw_status_t app_update_1ms(void) {\n    efw_status_t s;\n    ++g_app_tick_ms;\n")
    for flow in ctx["flows"]:
        ident = c_ident(flow["id"])
        period = int(flow.get("period_ms", 1))
        condition = "1" if period <= 1 else f"(g_app_tick_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = efw_line_follower_update(&g_{ident}, 0, 0);\n        if (s != EFW_OK) return s;\n    }}\n")
    for task in ctx["tasks"]:
        period = int(task.get("period_ms", 1))
        condition = "1" if period <= 1 else f"(g_app_tick_ms % {period}u) == 0u"
        if task.get("call"):
            parts.append(f"    if ({condition}) {{\n        s = {c_ident(task['call'])}();\n        if (s != EFW_OK) return s;\n    }}\n")
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

efw_status_t app_loop_1ms(void) {
    return efw_app_update_1ms(&g_app_manifest);
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
    custom_c_files = [item["path"] for item in ctx["custom_files"] if item["path"].endswith(".c")]
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


def generate(graph_path: Path, out_dir: Path, force: bool) -> None:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = validate_graph(graph)
    if out_dir.exists():
        require(force, f"output directory already exists: {out_dir} (pass --force to replace it)")
        shutil.rmtree(out_dir)
    write_file(out_dir, "app_board_config.h", render_board_config(ctx))
    write_file(out_dir, "app_manifest.h", render_manifest(ctx))
    write_file(out_dir, "app_components.h", render_components_h())
    write_file(out_dir, "app_components.c", render_components_c(ctx))
    write_file(out_dir, "app_platform.h", render_platform_h())
    write_file(out_dir, "app_platform.c", render_platform_c(ctx))
    write_file(out_dir, "app_bootstrap.h", render_bootstrap_h())
    write_file(out_dir, "app_bootstrap.c", render_bootstrap_c(ctx))
    write_file(out_dir, "main.c", render_main_c(ctx))
    for item in ctx["custom_files"]:
        write_file(out_dir, item["path"], item["content"])
    write_file(out_dir, "CMakeLists.generated.txt", render_cmake(ctx))


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
