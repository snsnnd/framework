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
from pathlib import Path

from codegen.validate import validate_graph


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


def nodes_of(ctx, type_name):
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


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
    for index, contract in enumerate(sorted(ctx.get("contracts", {}).values(), key=lambda item: item["name"]), start=1):
        lines.append(f"#define APP_CONTRACT_{macro_ident(contract['name'])} {index}u /* c_type={contract.get('c_type', contract.get('type', 'custom'))}; size={int(contract.get('size', 0) or 0)} */")
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
#define APP_USE_PROCESSOR           {c_bool(len(nodes_of(ctx, 'processor.custom')))}
#define APP_USE_MODULE              {c_bool(len(nodes_of(ctx, 'module.custom')))}
#define APP_USE_EVENT               {c_bool(len(nodes_of(ctx, 'event.topic') + nodes_of(ctx, 'event.publisher') + nodes_of(ctx, 'event.subscriber')))}
#define APP_USE_STATE_MACHINE       {c_bool(len(nodes_of(ctx, 'state.machine') + nodes_of(ctx, 'state.state') + nodes_of(ctx, 'state.transition')))}

#define APP_PROJECT_TICK_MS          {int(ctx["project"].get("tick_ms", 1))}u

#define APP_HAL_COUNT               {len(nodes_of(ctx, 'hal.gpio_line_input') + nodes_of(ctx, 'hal.custom'))}
#define APP_SENSOR_COUNT            {len(nodes_of(ctx, 'sensor.line_tracking') + nodes_of(ctx, 'sensor.custom'))}
#define APP_ACTUATOR_COUNT          {len(nodes_of(ctx, 'actuator.motor') + nodes_of(ctx, 'actuator.custom'))}
#define APP_ALGO_COUNT              {len(nodes_of(ctx, 'algorithm.pid') + nodes_of(ctx, 'algorithm.custom'))}
#define APP_PROCESSOR_COUNT         {len(nodes_of(ctx, 'processor.custom'))}
#define APP_DATAFLOW_PIPELINE_COUNT {len(dataflow_paths(ctx))}
#define APP_DATAFLOW_BUFFER_SIZE    {dataflow_buffer_size(ctx)}u
#define APP_MODULE_COUNT            {len(nodes_of(ctx, 'module.custom'))}
#define APP_TOPIC_COUNT             {len(nodes_of(ctx, 'event.topic'))}
#define APP_CONTRACT_COUNT          {len(ctx.get("contracts", {}))}
#define APP_STATE_COUNT             {len(nodes_of(ctx, 'state.state'))}

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
    if not line_inputs:
        parts.append("    (void)count;\n")
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
    if machines:
        parts.append("static efw_status_t app_noop_status(void *ctx) { EFW_UNUSED(ctx); return EFW_OK; }\n")
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
        parts.append(f"static uint32_t g_{m_ident}_entered_ms;\n")
        parts.append(f"static efw_status_t app_{m_ident}_register(void) {{\n    efw_status_t s;\n")
        for state in states:
            parts.append(f"    s = efw_sm_register(&g_state_{c_ident(state['id'])});\n    if (s != EFW_OK) return s;\n")
        if states:
            parts.append(f"    if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
            parts.append(f"    g_{m_ident}_entered_ms = g_app_elapsed_ms;\n")
        parts.append("    return EFW_OK;\n}\n")
        parts.append(f"static efw_status_t app_{m_ident}_tick(void) {{\n    efw_status_t s;\n")
        if states:
            parts.append(f"    s = g_{m_ident}_states[g_{m_ident}_current]->on_tick(g_{m_ident}_states[g_{m_ident}_current]->ctx);\n    if (s != EFW_OK) return s;\n")
            ordered_transitions = sorted(bundle["transitions"], key=lambda item: int(item.get("priority", 0)))
            for transition in ordered_transitions:
                cond_parts = [c_ident(transition["condition"]) + "()"]
                timeout_ms = int(transition.get("timeout_ms", 0))
                if timeout_ms > 0:
                    cond_parts.append(f"((g_app_elapsed_ms - g_{m_ident}_entered_ms) >= {timeout_ms}u)")
                cond = " && ".join(cond_parts)
                from_idx = index.get(transition.get("from"), 0)
                to_idx = index.get(transition.get("to"), 0)
                if transition.get("event_trigger"):
                    event_note = str(transition.get("event_trigger")).replace("*/", "* /")
                    parts.append(f"    /* event_trigger: {event_note} */\n")
                parts.append(f"    if (g_{m_ident}_current == {from_idx}u && ({cond})) {{\n")
                parts.append(f"        if (g_{m_ident}_states[g_{m_ident}_current]->on_exit) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_exit(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n")
                if transition.get("action"):
                    parts.append(f"        s = {c_ident(transition['action'])}();\n        if (s != EFW_OK) return s;\n")
                parts.append(f"        g_{m_ident}_current = {to_idx}u;\n")
                parts.append(f"        g_{m_ident}_entered_ms = g_app_elapsed_ms;\n")
                parts.append(f"        if (g_{m_ident}_states[g_{m_ident}_current]->on_enter) {{ s = g_{m_ident}_states[g_{m_ident}_current]->on_enter(g_{m_ident}_states[g_{m_ident}_current]->ctx); if (s != EFW_OK) return s; }}\n        break;\n    }}\n")
        parts.append("    return EFW_OK;\n}\n\n")
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
        parts.append(f"    s = efw_sensor_read({c_str(first['id'])}, {current});\n")
        parts.append("    if (s != EFW_OK) return s;\n")
        for node_id in path[1:]:
            node = ctx["nodes_by_id"][node_id]
            node_type = node.get("type")
            if node_type == "processor.custom":
                parts.append(f"    s = app_processor_{c_ident(node['id'])}({current}, {scratch});\n")
                parts.append("    if (s != EFW_OK) return s;\n")
                current, scratch = scratch, current
            elif node_type in {"algorithm.pid", "algorithm.custom"}:
                parts.append(f"    s = efw_algo_run({c_str(node['id'])}, {current}, {scratch});\n")
                parts.append("    if (s != EFW_OK) return s;\n")
                current, scratch = scratch, current
            elif node_type in {"actuator.motor", "actuator.custom"}:
                parts.append(f"    s = efw_actuator_write({c_str(node['id'])}, {current});\n")
                parts.append("    if (s != EFW_OK) return s;\n")
        parts.append("    return EFW_OK;\n")
        parts.append("}\n\n")
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

typedef union {
    uint8_t raw[APP_DATAFLOW_BUFFER_SIZE];
    float align_f;
    uint32_t align_u32;
    void *align_ptr;
} app_dataflow_buffer_t;

"""]
    parts.append(render_state_logic_blocks(ctx))
    parts.append(render_dataflow_pipelines(ctx))
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
    for index, path in enumerate(dataflow_paths(ctx), start=1):
        names = [c_ident(node_id) for node_id in path]
        fn = "app_dataflow_" + "_".join(names[:4])
        if len(names) > 4:
            fn += f"_{index}"
        period = dataflow_period_ms(ctx, path)
        condition = "1" if period <= int(ctx["project"].get("tick_ms", 1)) else f"(g_app_elapsed_ms % {period}u) == 0u"
        parts.append(f"    if ({condition}) {{\n        s = {fn}();\n        if (s != EFW_OK) return s;\n    }}\n")
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
    ctx = validate_graph(graph)
    if out_dir.exists() and any(out_dir.iterdir()):
        require(force, f"output directory already exists: {out_dir} (pass --force to overwrite generated files; non-generated files are preserved)")
    for rel_path, content in render_application_files(ctx).items():
        target = out_dir / rel_path
        if target.exists() and target.read_text(encoding="utf-8") != content:
            backup = out_dir / ".efw_backup" / rel_path
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        write_file(out_dir, rel_path, content)
