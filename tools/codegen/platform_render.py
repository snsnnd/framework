"""Platform HAL/sensor/actuator render helpers."""

from __future__ import annotations

try:
    from .utils import c_ident, c_str
except ImportError:  # pragma: no cover
    from codegen.utils import c_ident, c_str


def hal_type_expr(node):
    mapping = {
        "gpio": "EFW_HAL_GPIO",
        "i2c": "EFW_HAL_I2C",
        "spi": "EFW_HAL_SPI",
        "uart": "EFW_HAL_UART",
        "timer": "EFW_HAL_TIMER",
        "adc": "EFW_HAL_ADC",
        "pwm": "EFW_HAL_PWM",
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


def render_hal_runtime_defs(hal_runtime_model):
    parts = []
    for item in hal_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "line_input":
            macro = item["macro"]
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
        else:
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
    return "".join(parts)


def render_sensor_runtime_defs(sensor_runtime_model):
    parts = []
    for item in sensor_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "line_sensor":
            input_node = item["input_node"]
            parts.append(f"""static efw_sensor_ops_t g_{ident}_sensor = {{
    .name = {c_str(node['id'])},
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = {int(input_node['channels'])}u,
    .hal_name = {c_str(node['input'])},
    .ctx = (void *){c_str(node['input'])},
    .read = line_sensor_read,
}};

""")
        else:
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
    return "".join(parts)


def render_actuator_runtime_defs(actuator_runtime_model):
    parts = []
    for item in actuator_runtime_model:
        node = item["node"]
        ident = item["ident"]
        if item["kind"] == "motor":
            macro = item["macro"]
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
        else:
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
    return "".join(parts)


def render_platform_registrations(hal_runtime_model, sensor_runtime_model, actuator_runtime_model):
    parts = ["efw_status_t app_platform_register(void) {\n    efw_status_t s;\n"]
    for item in hal_runtime_model:
        parts.append(f"    s = efw_hal_register(&g_{item['ident']}_hal);\n    if (s != EFW_OK) return s;\n")
    for item in sensor_runtime_model:
        parts.append(f"    s = efw_sensor_register(&g_{item['ident']}_sensor);\n    if (s != EFW_OK) return s;\n")
    for item in actuator_runtime_model:
        suffix = "motor" if item["kind"] == "motor" else "actuator"
        parts.append(f"    s = efw_actuator_register(&g_{item['ident']}_{suffix});\n    if (s != EFW_OK) return s;\n")
    parts.append("    return EFW_OK;\n}\n\n")
    return "".join(parts)
