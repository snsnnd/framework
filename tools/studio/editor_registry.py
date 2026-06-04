#!/usr/bin/env python3
"""Template registry and field metadata for the Studio editor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio.core import discover_framework_templates
from studio.model import VISUAL_NODE_CATEGORIES

TYPE_LABELS = {
    "hal.gpio_line_input": "HAL · GPIO循迹输入",
    "hal.custom": "HAL · 自定义外设",
    "sensor.line_tracking": "传感器 · 循迹",
    "sensor.custom": "传感器 · 自定义",
    "actuator.motor": "执行器 · 电机",
    "actuator.custom": "执行器 · 自定义",
    "algorithm.pid": "算法 · PID",
    "algorithm.custom": "算法 · 自定义",
    "processor.custom": "处理器 · 自定义",
    "module.custom": "业务模块 · 生命周期",
    "task.periodic": "任务 · 周期",
    "project.module": "项目 · 模块分组",
    "event.topic": "通信 · Topic",
    "event.publisher": "通信 · 发布者",
    "event.subscriber": "通信 · 订阅者",
    "state.machine": "状态机 · 容器",
    "state.state": "状态机 · 状态",
    "state.transition": "状态机 · 转换",
    "data.enum": "数据 · enum枚举",
    "data.struct": "数据 · struct结构体",
    "custom.card": "说明卡片",
    "custom.code": "代码卡片",
}

NODE_TEMPLATES: dict[str, dict[str, Any]] = {
    "hal.gpio_line_input": {
        "id": "line_input",
        "type": "hal.gpio_line_input",
        "channels": 5,
        "pins": [
            {"port": "A", "pin": 0},
            {"port": "A", "pin": 1},
            {"port": "A", "pin": 2},
            {"port": "A", "pin": 3},
            {"port": "A", "pin": 4},
        ],
    },
    "hal.custom": {
        "id": "uart_debug",
        "type": "hal.custom",
        "hal_type": "uart",
        "bus_id": 1,
        "ctx": "0",
        "init": "app_uart_debug_init",
        "write": "app_uart_debug_write",
    },
    "sensor.line_tracking": {
        "id": "line_sensor_5ch",
        "type": "sensor.line_tracking",
        "input": "line_input",
    },
    "actuator.motor": {
        "id": "motor",
        "type": "actuator.motor",
        "pwm": {"timer": 1, "channel": 1},
        "dir_pin": {"port": "B", "pin": 0},
    },
    "actuator.custom": {
        "id": "status_led",
        "type": "actuator.custom",
        "actuator_type": "led",
        "ctx": "0",
        "write": "app_status_led_write",
    },
    "algorithm.pid": {
        "id": "line_pid",
        "type": "algorithm.pid",
        "input_type": "float",
        "output_type": "float",
        "output_desc": "PID control value",
        "kp": 18.0,
        "ki": 0.0,
        "kd": 2.5,
        "kff": 0.0,
        "integral_min": -20.0,
        "integral_max": 20.0,
        "out_min": -60.0,
        "out_max": 60.0,
        "anti_windup": True,
    },
    "sensor.custom": {
        "id": "custom_sensor",
        "type": "sensor.custom",
        "sensor_type": "custom",
        "output_type": "float",
        "output_desc": "sensor sample",
        "channel_count": 1,
        "hal_name": "",
        "comm_name": "",
        "ctx": "0",
        "read": "app_custom_sensor_read",
    },
    "algorithm.custom": {
        "id": "custom_algo",
        "type": "algorithm.custom",
        "algo_type": "EFW_ALGO_CUSTOM",
        "input_type": "custom",
        "output_type": "custom",
        "output_desc": "algorithm output",
        "ctx": "0",
        "run": "app_custom_algo_run",
        "io_contract": "custom",
    },
    "processor.custom": {
        "id": "custom_processor",
        "type": "processor.custom",
        "input_contract": "raw_bytes",
        "output_contract": "efw_pid_input_t",
        "input_type": "uint8_t",
        "output_type": "efw_pid_input_t",
        "input_size": 8,
        "output_size": 16,
        "output_desc": "normalized processor output",
        "ctx": "0",
        "process": "app_custom_processor_process",
        "description": "把模块内部原始数据转换为下游算法/执行器需要的标准数据契约。",
    },
    "module.custom": {
        "id": "custom_module",
        "type": "module.custom",
        "module_type": "EFW_MODULE_CUSTOM",
        "input_type": "custom",
        "output_type": "custom",
        "output_desc": "module side effect or data output",
        "ctx": "0",
        "init": "app_custom_module_init",
        "start": "",
        "stop": "",
        "poll": "app_custom_module_poll",
    },
    "task.periodic": {
        "id": "custom_task_10ms",
        "type": "task.periodic",
        "period_ms": 10,
        "call": "app_custom_task_10ms",
    },
    "project.module": {
        "id": "control_module",
        "type": "project.module",
        "display_name": "控制模块",
        "description": "用于把一组 HAL/Sensor/Algorithm/Task 归到同一个应用模块或子系统。",
        "inputs": [],
        "outputs": [],
        "subgraph": {"nodes": [], "edges": []},
    },
    "event.topic": {
        "id": "topic_battery",
        "type": "event.topic",
        "topic_id": 1,
        "payload_type": "float",
        "description": "电池电压事件",
    },
    "event.publisher": {
        "id": "publish_battery",
        "type": "event.publisher",
        "topic": "topic_battery",
        "source": "battery_sensor",
        "data_type": "float",
        "data_expr": "&battery_voltage",
        "size_expr": "sizeof(battery_voltage)",
        "interval_ms": 0,
    },
    "event.subscriber": {
        "id": "subscribe_battery",
        "type": "event.subscriber",
        "topic": "topic_battery",
        "target": "health_service",
        "callback": "app_on_battery_topic",
        "user": "0",
    },
    "state.machine": {
        "id": "main_state_machine",
        "type": "state.machine",
        "initial": "idle",
        "description": "状态机容器，生成 EFW state_machine 注册和轻量转换调度。",
    },
    "state.state": {
        "id": "idle",
        "type": "state.state",
        "machine": "main_state_machine",
        "on_enter": "",
        "on_update": "",
        "on_exit": "",
    },
    "state.transition": {
        "id": "idle_to_run",
        "type": "state.transition",
        "machine": "main_state_machine",
        "from": "idle",
        "to": "run",
        "condition": "app_can_run",
        "priority": 0,
        "action": "",
        "timeout_ms": 0,
        "event_trigger": "",
    },
    "data.enum": {
        "id": "enum_type",
        "type": "data.enum",
        "name": "app_state_t",
        "data_type": "enum",
        "values": ["APP_STATE_IDLE", "APP_STATE_RUN", "APP_STATE_ERROR"],
        "description": "Project enum type. Define the C enum in custom_files.",
    },
    "data.struct": {
        "id": "struct_type",
        "type": "data.struct",
        "name": "app_payload_t",
        "data_type": "struct",
        "fields": [{"type": "uint16_t", "name": "value"}],
        "description": "Project struct type. Define the C struct in custom_files.",
    },
    "custom.card": {
        "id": "custom_note",
        "type": "custom.card",
        "note": "Documentation-only card for hardware, tuning notes, or future generator templates.",
    },
    "custom.code": {
        "id": "custom_code_note",
        "type": "custom.code",
        "note": "Use the Code tab to add custom .c/.h files. This card documents the custom extension point.",
    },
}


def framework_scan_categories() -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    labels = {"hal": "框架扫描 · HAL", "sensor": "框架扫描 · 传感器", "actuator": "框架扫描 · 执行器", "algorithm": "框架扫描 · 算法", "module": "框架扫描 · 模块", "event": "框架扫描 · 通信", "state": "框架扫描 · 状态机"}
    for key in FRAMEWORK_SCAN_ORDER:
        module = str(NODE_TEMPLATES.get(key, {}).get("library_module", "other"))
        grouped.setdefault(module, []).append(key)
    return [(labels.get(module, f"框架扫描 · {module}"), keys) for module, keys in grouped.items()]


PROPERTY_FIELD_ORDER = {
    "project.module": ["id", "type", "display_name", "parent", "inputs", "outputs", "description"],
    "hal.custom": ["id", "type", "module", "hal_type", "ctx_name", "init", "read", "write", "ioctl"],
    "hal.gpio_line_input": ["id", "type", "module", "channels", "pins"],
    "sensor.custom": ["id", "type", "module", "sensor_type", "output_contract", "output_type", "output_size", "output_align", "output_desc", "hal_name", "ctx_name", "init", "read"],
    "sensor.line_tracking": ["id", "type", "module", "input", "channels", "active_value", "binary_mode"],
    "actuator.custom": ["id", "type", "module", "actuator_type", "input_contract", "input_type", "input_size", "input_align", "hal_name", "ctx_name", "init", "enable", "disable", "write"],
    "actuator.motor": ["id", "type", "module", "pwm", "dir_pin", "max_speed"],
    "algorithm.pid": ["id", "type", "module", "input_type", "output_type", "output_desc", "kp", "ki", "kd", "out_min", "out_max", "integral_min", "integral_max", "anti_windup"],
    "algorithm.custom": ["id", "type", "module", "algo_type", "input_contract", "output_contract", "input_type", "output_type", "input_size", "output_size", "output_desc", "run", "ctx_name", "io_contract"],
    "processor.custom": ["id", "type", "module", "input_contract", "output_contract", "input_type", "output_type", "input_size", "output_size", "input_align", "output_align", "output_desc", "process", "ctx_name", "description"],
    "module.custom": ["id", "type", "module", "module_type", "input_type", "output_type", "output_desc", "ctx_name", "init", "start", "stop", "poll"],
    "task.periodic": ["id", "type", "module", "period_ms", "call", "flow"],
    "event.topic": ["id", "type", "module", "topic_id", "payload_type", "description"],
    "event.publisher": ["id", "type", "module", "topic", "source", "data_type", "data_expr", "size_expr", "interval_ms"],
    "event.subscriber": ["id", "type", "module", "topic", "target", "callback", "user"],
    "state.machine": ["id", "type", "module", "initial", "description"],
    "state.state": ["id", "type", "machine", "on_enter", "on_update", "on_exit"],
    "state.transition": ["id", "type", "machine", "from", "to", "condition", "priority", "action", "timeout_ms", "event_trigger"],
    "data.enum": ["id", "type", "name", "description", "module", "data_type", "values"],
    "data.struct": ["id", "type", "name", "description", "module", "data_type", "fields"],
}


def display_label(template_key: str) -> str:
    template = NODE_TEMPLATES.get(template_key, {})
    node_type = template.get("type", template_key)
    if template_key.startswith("scan."):
        return f"框架扫描 · {template.get('id', template_key)}"
    return TYPE_LABELS.get(node_type, TYPE_LABELS.get(template_key, template_key))


def build_node_categories() -> list[tuple[str, list[str]]]:
    categories = []
    for name, types in VISUAL_NODE_CATEGORIES:
        if name == "框架库扫描":
            categories.extend(framework_scan_categories())
        else:
            categories.append((name, types))
    return categories


FRAMEWORK_SCAN_TEMPLATES, FRAMEWORK_SCAN_ORDER = discover_framework_templates(NODE_TEMPLATES, Path(__file__).resolve().parents[2])
NODE_TEMPLATES.update(FRAMEWORK_SCAN_TEMPLATES)
NODE_CATEGORIES = build_node_categories()
