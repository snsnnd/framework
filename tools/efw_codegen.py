#!/usr/bin/env python3
"""Generate EFW application code from a small graph JSON file.

The first generator milestone intentionally targets the line-tracking-car MVP:
GPIO line input + line-tracking sensor + two motors + PID + line follower loop.
It produces the same application-layer shape as application/line_tracking_car,
leaving real chip SDK calls as TODOs inside app_platform.c.
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
    "actuator.motor",
    "algorithm.pid",
}
SUPPORTED_FLOW_TYPES = {"control.line_follower"}


def c_ident(value: str, fallback: str = "app") -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", value or fallback)
    ident = re.sub(r"_+", "_", ident).strip("_") or fallback
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


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


def index_nodes(nodes):
    result = {}
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        require(isinstance(node_id, str) and node_id, "each node needs a non-empty string id")
        require(node_type in SUPPORTED_NODE_TYPES, f"unsupported node type for {node_id}: {node_type}")
        require(node_id not in result, f"duplicate node id: {node_id}")
        result[node_id] = node
    return result


def get_single(nodes_by_id, node_type):
    matches = [node for node in nodes_by_id.values() if node.get("type") == node_type]
    require(len(matches) == 1, f"expected exactly one {node_type} node, got {len(matches)}")
    return matches[0]


def validate_graph(graph):
    require(isinstance(graph, dict), "graph root must be an object")
    project = graph.get("project", {})
    require(isinstance(project, dict), "project must be an object")
    project_name = project.get("name", "generated_line_tracking_car")
    require(isinstance(project_name, str) and project_name, "project.name must be a non-empty string")

    nodes = graph.get("nodes")
    flows = graph.get("flows")
    require(isinstance(nodes, list) and nodes, "nodes must be a non-empty array")
    require(isinstance(flows, list) and len(flows) == 1, "flows must contain exactly one flow for the MVP generator")

    nodes_by_id = index_nodes(nodes)
    flow = flows[0]
    require(flow.get("type") in SUPPORTED_FLOW_TYPES, f"unsupported flow type: {flow.get('type')}")

    line_input = nodes_by_id.get(flow.get("line_input")) or get_single(nodes_by_id, "hal.gpio_line_input")
    sensor = nodes_by_id.get(flow.get("sensor"))
    pid = nodes_by_id.get(flow.get("pid"))
    left_motor = nodes_by_id.get(flow.get("left_motor"))
    right_motor = nodes_by_id.get(flow.get("right_motor"))

    require(sensor and sensor.get("type") == "sensor.line_tracking", "flow.sensor must reference a sensor.line_tracking node")
    require(pid and pid.get("type") == "algorithm.pid", "flow.pid must reference an algorithm.pid node")
    require(left_motor and left_motor.get("type") == "actuator.motor", "flow.left_motor must reference an actuator.motor node")
    require(right_motor and right_motor.get("type") == "actuator.motor", "flow.right_motor must reference an actuator.motor node")
    require(sensor.get("input") == line_input.get("id"), "sensor.input must reference the gpio line input node")

    channels = int(line_input.get("channels", 0))
    pins = line_input.get("pins", [])
    weights = flow.get("weights", [])
    require(channels > 0, "line input channels must be > 0")
    require(len(pins) == channels, "line input pins length must equal channels")
    require(len(weights) == channels, "line follower weights length must equal channels")
    require(float(flow.get("dt", 0.0)) > 0.0, "line follower dt must be > 0")

    for motor in (left_motor, right_motor):
        require(isinstance(motor.get("pwm"), dict), f"{motor['id']}.pwm must be an object")
        require(isinstance(motor.get("dir_pin"), dict), f"{motor['id']}.dir_pin must be an object")

    return {
        "project": project,
        "line_input": line_input,
        "sensor": sensor,
        "pid": pid,
        "left_motor": left_motor,
        "right_motor": right_motor,
        "flow": flow,
        "channels": channels,
    }


def pin_expr(pin):
    port = str(pin.get("port", "A")).upper()
    require(port in {"A", "B", "C"}, f"unsupported GPIO port: {port}")
    return f"{{ APP_GPIO_PORT_{port}, {int(pin.get('pin', 0))}u }}"


def pwm_expr(pwm):
    return f"{{ {int(pwm.get('timer', 1))}u, {int(pwm.get('channel', 1))}u }}"


def write_file(out_dir: Path, name: str, content: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_text(content.rstrip() + "\n", encoding="utf-8")


def render_board_config(ctx):
    line_input = ctx["line_input"]
    flow = ctx["flow"]
    left = ctx["left_motor"]
    right = ctx["right_motor"]
    pins = ",\n    ".join(pin_expr(pin) for pin in line_input["pins"])

    return f"""
/**
 * @file    app_board_config.h
 * @brief   Generated board-level constants for an EFW line-tracking application.
 *
 * Generated by tools/efw_codegen.py. Replace the mock platform callbacks in
 * app_platform.c with STM32 HAL, ESP-IDF, MSPM0 DriverLib, or your BSP calls.
 */

#ifndef APP_BOARD_CONFIG_H
#define APP_BOARD_CONFIG_H

#include <stdint.h>

#define APP_LINE_CHANNELS {ctx['channels']}

typedef struct {{
    uint8_t port;
    uint16_t pin;
}} app_gpio_pin_t;

typedef struct {{
    uint8_t timer_id;
    uint8_t channel;
}} app_pwm_channel_t;

#define APP_GPIO_PORT_A 0u
#define APP_GPIO_PORT_B 1u
#define APP_GPIO_PORT_C 2u

static const app_gpio_pin_t APP_LINE_PINS[APP_LINE_CHANNELS] = {{
    {pins},
}};

#define APP_LEFT_MOTOR_PWM  ((app_pwm_channel_t){pwm_expr(left['pwm'])})
#define APP_LEFT_MOTOR_DIR  ((app_gpio_pin_t){pin_expr(left['dir_pin'])})
#define APP_RIGHT_MOTOR_PWM ((app_pwm_channel_t){pwm_expr(right['pwm'])})
#define APP_RIGHT_MOTOR_DIR ((app_gpio_pin_t){pin_expr(right['dir_pin'])})

#define APP_LINE_ACTIVE_VALUE {int(flow.get('active_value', 1))}u
#define APP_LINE_BASE_SPEED   {c_float(flow.get('base_speed', 65.0))}
#define APP_LINE_MIN_SPEED    {c_float(flow.get('min_speed', 0.0))}
#define APP_LINE_MAX_SPEED    {c_float(flow.get('max_speed', 100.0))}
#define APP_LINE_DT_SECONDS   {c_float(flow.get('dt', 0.001))}

#endif
"""


def render_manifest(ctx):
    line_input = ctx["line_input"]
    sensor = ctx["sensor"]
    pid = ctx["pid"]
    left = ctx["left_motor"]
    right = ctx["right_motor"]
    flow = ctx["flow"]

    return f"""
/**
 * @file    app_manifest.h
 * @brief   Generated application manifest: feature switches, capacities, names, and policy.
 */

#ifndef APP_MANIFEST_H
#define APP_MANIFEST_H

#include "app_board_config.h"

#define APP_USE_HAL                 1
#define APP_USE_SENSOR              1
#define APP_USE_LINE_TRACKING       1
#define APP_USE_ACTUATOR            1
#define APP_USE_MOTOR               1
#define APP_USE_ALGORITHM           1
#define APP_USE_PID                 1

#define APP_HAL_COUNT               1
#define APP_SENSOR_COUNT            1
#define APP_ACTUATOR_COUNT          2
#define APP_ALGO_COUNT              1

#define APP_LINE_INPUT_HAL_NAME     "{line_input['id']}"
#define APP_LINE_SENSOR_NAME        "{sensor['id']}"
#define APP_LINE_PID_NAME           "{pid['id']}"
#define APP_LEFT_MOTOR_NAME         "{left['id']}"
#define APP_RIGHT_MOTOR_NAME        "{right['id']}"

#define APP_LINE_FOLLOWER_BINARY    {c_bool(flow.get('binary_mode', True))}

#endif
"""


def render_components_h():
    return """
/**
 * @file    app_components.h
 * @brief   Generated algorithm-component registration entry point.
 */

#ifndef APP_COMPONENTS_H
#define APP_COMPONENTS_H

#include "efw/efw.h"

efw_status_t app_components_register(void);

#endif
"""


def render_components_c(ctx):
    pid = ctx["pid"]
    return f"""
/**
 * @file    app_components.c
 * @brief   Generated PID component registration.
 */

#include "app_components.h"
#include "app_manifest.h"

static efw_pid_t g_line_pid = {{
    .kp = {c_float(pid.get('kp', 18.0))},
    .ki = {c_float(pid.get('ki', 0.0))},
    .kd = {c_float(pid.get('kd', 2.5))},
    .kff = {c_float(pid.get('kff', 0.0))},
    .integral_min = {c_float(pid.get('integral_min', -20.0))},
    .integral_max = {c_float(pid.get('integral_max', 20.0))},
    .out_min = {c_float(pid.get('out_min', -60.0))},
    .out_max = {c_float(pid.get('out_max', 60.0))},
    .anti_windup = {c_bool(pid.get('anti_windup', True))},
}};

static efw_algo_ops_t g_line_pid_algo = {{
    .name = APP_LINE_PID_NAME,
    .type = EFW_ALGO_CONTROL,
    .ctx = &g_line_pid,
    .run = efw_pid_run,
}};

efw_status_t app_components_register(void) {{
    return efw_algo_register(&g_line_pid_algo);
}}
"""


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
void app_platform_set_line_state(const uint16_t values[APP_LINE_CHANNELS]);

#endif
"""


def render_platform_c(ctx):
    return """
/**
 * @file    app_platform.c
 * @brief   Generated mock platform layer for EFW line tracking.
 *
 * TODO(real board): replace line_input_read() and motor_write() internals with
 * concrete chip SDK/BSP calls. The generated registration and names can stay.
 */

#include "app_platform.h"
#include "app_manifest.h"

typedef struct {
    uint16_t channel[APP_LINE_CHANNELS];
    const app_gpio_pin_t *pins;
} app_line_input_ctx_t;

typedef struct {
    app_pwm_channel_t pwm;
    app_gpio_pin_t dir_pin;
    float last_speed;
    float last_direction;
} app_motor_ctx_t;

static app_line_input_ctx_t g_line_input = {
    .pins = APP_LINE_PINS,
};
static app_motor_ctx_t g_left_motor_ctx = {
    .pwm = APP_LEFT_MOTOR_PWM,
    .dir_pin = APP_LEFT_MOTOR_DIR,
};
static app_motor_ctx_t g_right_motor_ctx = {
    .pwm = APP_RIGHT_MOTOR_PWM,
    .dir_pin = APP_RIGHT_MOTOR_DIR,
};

static efw_status_t line_input_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    app_line_input_ctx_t *input = (app_line_input_ctx_t *)ctx;
    efw_line_tracking_data_t *out = (efw_line_tracking_data_t *)buf;

    if (!input || !out || len < sizeof(efw_line_tracking_data_t)) return EFW_ERR_INVALID;

    out->count = APP_LINE_CHANNELS;
    for (uint8_t i = 0; i < APP_LINE_CHANNELS; ++i) {
        out->value[i] = input->channel[i];
    }

    if (actual) *actual = sizeof(efw_line_tracking_data_t);
    return EFW_OK;
}

static efw_status_t line_sensor_read(void *ctx, void *out) {
    EFW_UNUSED(ctx);
    return efw_hal_read(APP_LINE_INPUT_HAL_NAME, out, sizeof(efw_line_tracking_data_t), 0);
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

static efw_hal_ops_t g_line_input_hal = {
    .name = APP_LINE_INPUT_HAL_NAME,
    .type = EFW_HAL_GPIO,
    .bus_id = 1,
    .ctx = &g_line_input,
    .read = line_input_read,
};

static efw_sensor_ops_t g_line_sensor = {
    .name = APP_LINE_SENSOR_NAME,
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = APP_LINE_CHANNELS,
    .hal_name = APP_LINE_INPUT_HAL_NAME,
    .read = line_sensor_read,
};

static efw_actuator_ops_t g_left_motor = {
    .name = APP_LEFT_MOTOR_NAME,
    .type = EFW_ACTUATOR_MOTOR,
    .ctx = &g_left_motor_ctx,
    .write = motor_write,
};

static efw_actuator_ops_t g_right_motor = {
    .name = APP_RIGHT_MOTOR_NAME,
    .type = EFW_ACTUATOR_MOTOR,
    .ctx = &g_right_motor_ctx,
    .write = motor_write,
};

efw_status_t app_platform_register(void) {
    efw_status_t s;

    s = efw_hal_register(&g_line_input_hal);
    if (s != EFW_OK) return s;
    s = efw_sensor_register(&g_line_sensor);
    if (s != EFW_OK) return s;
    s = efw_actuator_register(&g_left_motor);
    if (s != EFW_OK) return s;
    return efw_actuator_register(&g_right_motor);
}

void app_platform_set_line_state(const uint16_t values[APP_LINE_CHANNELS]) {
    if (!values) return;
    for (uint8_t i = 0; i < APP_LINE_CHANNELS; ++i) {
        g_line_input.channel[i] = values[i];
    }
}
"""


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
    weights = ", ".join(c_float(value) for value in ctx["flow"]["weights"])
    return f"""
/**
 * @file    app_bootstrap.c
 * @brief   Generated glue code between the generic runtime and line follower graph.
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

static efw_line_follower_t g_line_follower;
static const float g_line_weights[APP_LINE_CHANNELS] = {{ {weights} }};

static efw_status_t app_init_pools(void) {{
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
}}

static efw_status_t app_bind_handles(void) {{
    const efw_line_follower_config_t config = {{
        .sensor_name = APP_LINE_SENSOR_NAME,
        .pid_name = APP_LINE_PID_NAME,
        .left_motor = APP_LEFT_MOTOR_NAME,
        .right_motor = APP_RIGHT_MOTOR_NAME,
        .weights = g_line_weights,
        .base_speed = APP_LINE_BASE_SPEED,
        .min_speed = APP_LINE_MIN_SPEED,
        .max_speed = APP_LINE_MAX_SPEED,
        .dt = APP_LINE_DT_SECONDS,
        .active_value = APP_LINE_ACTIVE_VALUE,
        .binary_mode = APP_LINE_FOLLOWER_BINARY,
    }};

    return efw_line_follower_bind_config(&g_line_follower, &config);
}}

static efw_status_t app_update_1ms(void) {{
    return efw_line_follower_update(&g_line_follower, 0, 0);
}}

static const efw_app_manifest_t g_app_manifest = {{
    .init_pools = app_init_pools,
    .register_platform = app_platform_register,
    .register_components = app_components_register,
    .bind_handles = app_bind_handles,
    .update_1ms = app_update_1ms,
}};

efw_status_t app_init(void) {{
    return efw_app_init(&g_app_manifest);
}}

efw_status_t app_loop_1ms(void) {{
    return efw_app_update_1ms(&g_app_manifest);
}}
"""


def render_main_c(ctx):
    centered = ["0"] * ctx["channels"]
    centered[ctx["channels"] // 2] = "1"
    centered_values = ", ".join(centered)
    return f"""
/**
 * @file    main.c
 * @brief   Generated host-checkable entry point for the EFW line-tracking app.
 */

#include "app_bootstrap.h"
#include "app_platform.h"

int main(void) {{
    const uint16_t centered_line[APP_LINE_CHANNELS] = {{ {centered_values} }};

    app_init();
    app_platform_set_line_state(centered_line);
    app_loop_1ms();

    return 0;
}}
"""


def render_cmake(ctx):
    target = c_ident(ctx["project"].get("name", "generated_line_tracking_car"))
    return f"""
# Optional generated-app CMake snippet.
# From the repository root, this app is already buildable by compiling the four
# generated .c files and linking them against the efw library.
add_executable(efw_app_{target}
    main.c
    app_bootstrap.c
    app_components.c
    app_platform.c
)
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
