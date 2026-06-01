#!/usr/bin/env python3
"""PyQt visual graph + code editor for the EFW application generator.

This is the second milestone of the blueprint workflow: users can create known
EFW cards visually, edit their JSON properties, write custom C/H files in the
same project, and invoke tools/efw.py codegen to export an application folder.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import QMimeData, QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence, QPen, QShortcut
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QGraphicsEllipseItem,
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsTextItem,
        QGraphicsView,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QLineEdit,
        QComboBox,
        QCheckBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabBar,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import QMimeData, QPointF, Qt
    from PyQt5.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence, QPen
    from PyQt5.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QGraphicsEllipseItem,
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsTextItem,
        QGraphicsView,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QLineEdit,
        QComboBox,
        QCheckBox,
        QPushButton,
        QPlainTextEdit,
        QShortcut,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabBar,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QApplication = None
    QFileDialog = QInputDialog = QMessageBox = None
    QBrush = QColor = QDrag = QFont = QFontMetrics = QKeySequence = QMimeData = QPen = QShortcut = QPointF = Qt = object
    QComboBox = QFormLayout = QGraphicsEllipseItem = QGraphicsItem = object
    QGraphicsLineItem = QGraphicsRectItem = QGraphicsScene = QGraphicsSimpleTextItem = QGraphicsTextItem = QGraphicsView = object
    QHBoxLayout = QLabel = QListWidget = QListWidgetItem = QMainWindow = object
    QLineEdit = QPushButton = QPlainTextEdit = QSplitter = QTableWidget = QTableWidgetItem = QCheckBox = object
    QTabBar = QTabWidget = QToolBar = QVBoxLayout = QWidget = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[2]

from codegen import c_ident, generate, preview_application_files
from codegen.validate import validate_graph
from codegen.graph import (
    PORT_COLORS,
    PORT_DESCRIPTIONS,
    PORT_LABELS,
    PORT_RULES,
    EDGE_KIND_LABELS,
    callback_signature,
    CALLBACK_SIGNATURES,
    NODE_CONTRACTS,
    apply_pair_semantics,
    can_connect_ports,
    pair_has_semantics,
    semantic_edge_kind,
    edge_effect_description,
    node_generation_label,
)
from studio.core import (
    apply_board_profile_defaults_to_graph,
    discover_framework_templates,
    node_summary,
    page_for_node,
    page_hint,
    page_key,
    page_title,
    root_page,
    visible_nodes_for_page,
    property_choices as core_property_choices,
)
from studio.model import BOARD_PROFILES, GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS, VISUAL_NODE_CATEGORIES



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

FRAMEWORK_SCAN_TEMPLATES, FRAMEWORK_SCAN_ORDER = discover_framework_templates(NODE_TEMPLATES, REPO_ROOT)
NODE_TEMPLATES.update(FRAMEWORK_SCAN_TEMPLATES)

DEFAULT_FLOW = {
    "id": "line_follower",
    "type": "control.line_follower",
    "sensor": "line_sensor_5ch",
    "pid": "line_pid",
    "left_motor": "left_motor",
    "right_motor": "right_motor",
    "weights": [-2.0, -1.0, 0.0, 1.0, 2.0],
    "base_speed": 65.0,
    "min_speed": 0.0,
    "max_speed": 100.0,
    "dt": 0.001,
    "active_value": 1,
    "binary_mode": True,
}

DEFAULT_CUSTOM_C = """/**
 * @file    app_custom.c
 * @brief   User code generated from the EFW visual editor.
 *
 * Put custom algorithms, modules, helper functions, or board glue here. If this
 * file should be compiled by CMake, keep the .c suffix; the generator adds it to
 * CMakeLists.generated.txt automatically.
 */

#include "efw/efw.h"

efw_status_t app_custom_algo_run(void *ctx, const void *in, void *out) {
    EFW_UNUSED(ctx);
    EFW_UNUSED(in);
    EFW_UNUSED(out);
    return EFW_OK;
}

efw_status_t app_uart_debug_init(void *ctx) {
    EFW_UNUSED(ctx);
    return EFW_OK;
}

efw_status_t app_uart_debug_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    EFW_UNUSED(ctx);
    EFW_UNUSED(buf);
    if (actual) *actual = len;
    return EFW_OK;
}

efw_status_t app_battery_sensor_read(void *ctx, void *out) {
    EFW_UNUSED(ctx);
    if (out) *(float *)out = 7.4f;
    return EFW_OK;
}

efw_status_t app_custom_sensor_read(void *ctx, void *out) {
    return app_battery_sensor_read(ctx, out);
}

efw_status_t app_status_led_write(void *ctx, const void *cmd) {
    EFW_UNUSED(ctx);
    EFW_UNUSED(cmd);
    return EFW_OK;
}

efw_status_t app_custom_module_init(void *ctx) {
    EFW_UNUSED(ctx);
    return EFW_OK;
}

efw_status_t app_custom_module_poll(void *ctx) {
    EFW_UNUSED(ctx);
    return EFW_OK;
}

efw_status_t app_custom_task_10ms(void) {
    return EFW_OK;
}

efw_status_t app_heartbeat_100ms(void) {
    return EFW_OK;
}

efw_status_t app_battery_sample_20ms(void) {
    return EFW_OK;
}

void app_on_battery_topic(uint16_t topic_id, const void *data, uint16_t size, void *user) {
    EFW_UNUSED(topic_id);
    EFW_UNUSED(data);
    EFW_UNUSED(size);
    EFW_UNUSED(user);
}
"""


NODE_THEMES = {
    "hal": {"bg": "#142534", "border": "#53b7d8", "accent": "#3aaed8"},
    "sensor": {"bg": "#172a21", "border": "#72d083", "accent": "#45c36c"},
    "actuator": {"bg": "#302414", "border": "#ffb766", "accent": "#f59e42"},
    "algorithm": {"bg": "#291d33", "border": "#c28cff", "accent": "#a66cff"},
    "processor": {"bg": "#13283a", "border": "#55c7ff", "accent": "#29a9e8"},
    "module": {"bg": "#2d2818", "border": "#f5d36a", "accent": "#d7ae36"},
    "task": {"bg": "#17253a", "border": "#6ea8fe", "accent": "#4c8dff"},
    "project": {"bg": "#221f3a", "border": "#9b8cff", "accent": "#7c6cff"},
    "event": {"bg": "#331d1f", "border": "#ff8a80", "accent": "#ff6b5f"},
    "state": {"bg": "#142b2a", "border": "#5ed6c9", "accent": "#35bdb2"},
    "custom": {"bg": "#242a36", "border": "#9aa8bd", "accent": "#7d8da6"},
}

WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { background: #0f1117; color: #e6e9ef; font-family: "Noto Sans CJK SC", "Microsoft YaHei", "SF Pro Display", "Segoe UI", "DejaVu Sans"; font-size: 10pt; }
QToolBar { background: #0f1117; border-bottom: 1px solid #242936; spacing: 8px; padding: 6px; }
QToolButton, QPushButton {
    background: #1c2333;
    color: #f4f7fb;
    border: 1px solid #2f3a52;
    border-radius: 10px;
    padding: 7px 12px;
}
QToolButton:hover, QPushButton:hover { background: #26324a; border-color: #5f8cff; }
QToolButton:pressed, QPushButton:pressed { background: #314063; }
QSplitter::handle { background: #171b26; }
#NavRail { background: #0b0d12; border-right: 1px solid #242936; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #151a24; color: #9ba7bd; padding: 8px 14px; border: 0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #6ea8fe; background: #111722; }
QListWidget, QTableWidget, QPlainTextEdit, QLineEdit, QComboBox {
    background: #151a24;
    color: #e6e9ef;
    border: 1px solid #242936;
    border-radius: 12px;
    selection-background-color: #355c9a;
    padding: 4px;
}
QListWidget::item { padding: 7px 8px; border-radius: 8px; }
QListWidget::item:selected { background: #25395f; color: #ffffff; }
QHeaderView::section { background: #1b2230; color: #c9d3e6; border: 0; padding: 6px; }
QLabel { color: #dce3f0; }
"""


def node_family(node_type: str | None) -> str:
    return str(node_type or "custom").split(".")[0]


def node_theme(node_type: str | None) -> dict[str, str]:
    return NODE_THEMES.get(node_family(node_type), NODE_THEMES["custom"])

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

def framework_scan_categories() -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    labels = {"hal": "框架扫描 · HAL", "sensor": "框架扫描 · 传感器", "actuator": "框架扫描 · 执行器", "algorithm": "框架扫描 · 算法", "module": "框架扫描 · 模块", "event": "框架扫描 · 通信", "state": "框架扫描 · 状态机"}
    for key in FRAMEWORK_SCAN_ORDER:
        module = str(NODE_TEMPLATES.get(key, {}).get("library_module", "other"))
        grouped.setdefault(module, []).append(key)
    return [(labels.get(module, f"框架扫描 · {module}"), keys) for module, keys in grouped.items()]


NODE_CATEGORIES = []
for name, types in VISUAL_NODE_CATEGORIES:
    if name == "框架库扫描":
        NODE_CATEGORIES.extend(framework_scan_categories())
    else:
        NODE_CATEGORIES.append((name, types))


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
    "event.publisher": ["id", "type", "module", "topic", "source", "data_type", "data_expr", "size_expr"],
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


def parse_form_value(text: str) -> Any:
    value = text.strip()
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        if value.startswith(("{", "[")):
            return json.loads(value)
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return text
    except json.JSONDecodeError:
        return text


def form_value_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def card_display_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("display_name") or node.get("title") or node.get("id") or "未命名")


def card_description(node: dict[str, Any]) -> str:
    return str(node.get("description") or node.get("note") or NODE_CONTRACTS.get(str(node.get("type")), {}).get("boundary", ""))


def card_port_lines(node: dict[str, Any]) -> list[str]:
    rules = PORT_RULES.get(node.get("type"), {})
    lines = []
    for label, key in [("输入", "in"), ("输出", "out")]:
        ports = rules.get(key, [])
        if ports:
            names = " / ".join(PORT_LABELS.get(port, port) for port in ports)
            lines.append(f"{label}: {names}")
    return lines


def card_ports_by_direction(node: dict[str, Any]) -> list[tuple[str, list[str]]]:
    rules = PORT_RULES.get(node.get("type"), {})
    result = []
    for label, key in [("输入", "in"), ("输出", "out")]:
        ports = rules.get(key, [])
        if ports:
            result.append((label, [PORT_LABELS.get(port, port) for port in ports]))
    return result


def compact_text(text: str, max_chars: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def add_wrapped_text(parent: QGraphicsItem, text: str, x: float, y: float, width: float, color: str, font_size: int = 9, bold: bool = False) -> QGraphicsTextItem:
    item = QGraphicsTextItem(compact_text(text, 180), parent)
    item.setDefaultTextColor(QColor(color))
    weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
    item.setFont(QFont("Sans", font_size, weight if bold else -1))
    item.setTextWidth(width)
    item.setPos(x, y)
    return item


class PortItem(QGraphicsRectItem):
    SIZE = 13

    def __init__(self, node_item: "GraphNodeItem", direction: str, port_type: str, index: int):
        super().__init__(0, 0, self.SIZE, self.SIZE, node_item)
        self.node_item = node_item
        self.direction = direction
        self.port_type = port_type
        base = QColor(PORT_COLORS.get(port_type, "#90a4ae"))
        self.setBrush(QBrush(base.lighter(115) if direction == "out" else base.darker(115)))
        self.setPen(QPen(QColor("#eef4ff"), 1.2))
        y = node_item.port_start_y + index * 22
        x = node_item.WIDTH - self.SIZE - 8 if direction == "out" else 8
        self.setPos(x, y)
        if port_type in {"topic", "event", "state_machine", "transition_from", "transition_to"}:
            self.setRotation(45)
        elif port_type in {"module_input", "module_output", "group", "code"}:
            self.setScale(1.15)
        self.setToolTip(node_item.editor.port_detail_tooltip(node_item.node, direction, port_type))
        self.setZValue(2)

    def mousePressEvent(self, event):
        self.node_item.editor.begin_port_drag(self)
        event.accept()

    def mouseMoveEvent(self, event):
        self.node_item.editor.update_port_drag(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.node_item.editor.finish_port_drag(event.scenePos(), self)
        event.accept()


class GraphNodeItem(QGraphicsRectItem):
    WIDTH = 170
    HEIGHT = 70

    def __init__(self, node: dict[str, Any], editor: "VisualEditorWindow"):
        summary_text = node_summary(node)
        title_text = card_display_name(node)
        node_id = str(node.get("id", "node"))
        label_text = TYPE_LABELS.get(node.get("type"), node.get("type", "unknown"))
        desc_text = card_description(node)
        port_groups = card_ports_by_direction(node)
        self.WIDTH = max(250, min(390, 96 + max(len(str(title_text)), len(str(label_text)), len(summary_text)) * 6))
        port_count = max(len(PORT_RULES.get(node.get("type"), {}).get("in", [])), len(PORT_RULES.get(node.get("type"), {}).get("out", [])))
        desc_height = 34 if desc_text else 0
        summary_height = 28 if summary_text else 0
        port_text_height = 26 * sum(len(ports) for _, ports in port_groups)
        self.port_start_y = 126 + summary_height + desc_height + port_text_height
        self.HEIGHT = max(self.port_start_y + max(port_count, 1) * 22 + 16, 168)
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.node = node
        self.editor = editor
        try:
            flags = (
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
        except AttributeError:
            flags = (
                QGraphicsItem.ItemIsMovable
                | QGraphicsItem.ItemIsSelectable
                | QGraphicsItem.ItemSendsGeometryChanges
            )
        self.setFlags(flags)
        theme = node_theme(node.get("type"))
        self.setBrush(QBrush(QColor(theme["bg"])))
        border_color = "#e53935" if node.get("type") == "state.transition" and not str(node.get("condition", "")).strip() else theme["border"]
        self.setPen(QPen(QColor(border_color), 2 if border_color == "#e53935" else 1.4))
        shadow = QGraphicsRectItem(5, 6, self.WIDTH, self.HEIGHT, self)
        shadow.setBrush(QBrush(QColor(0, 0, 0, 55)))
        shadow.setPen(QPen(QColor(0, 0, 0, 0), 0))
        shadow.setZValue(-1)
        accent = QGraphicsRectItem(0, 0, 6, self.HEIGHT, self)
        accent.setBrush(QBrush(QColor(theme["accent"])))
        accent.setPen(QPen(QColor(theme["accent"]), 0))
        title = QGraphicsSimpleTextItem(str(title_text), self)
        title.setBrush(QBrush(QColor("#f8fbff")))
        bold_weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
        title.setFont(QFont("Sans", 11, bold_weight))
        title_rect = title.boundingRect()
        title.setPos(max(14, (self.WIDTH - title_rect.width()) / 2), 12)
        subtitle = QGraphicsSimpleTextItem(label_text, self)
        subtitle.setBrush(QBrush(QColor("#b9c6d8")))
        subtitle_rect = subtitle.boundingRect()
        subtitle.setPos(max(14, (self.WIDTH - subtitle_rect.width()) / 2), 36)
        id_item = QGraphicsSimpleTextItem(f"ID  {node_id}", self)
        id_item.setBrush(QBrush(QColor("#7f8da5")))
        id_item.setFont(QFont("Sans", 8))
        id_rect = id_item.boundingRect()
        id_item.setPos(max(14, (self.WIDTH - id_rect.width()) / 2), 58)
        y_cursor = 82
        if summary_text:
            add_wrapped_text(self, "摘要：" + summary_text, 18, y_cursor, self.WIDTH - 36, "#aab7cc", 8)
            y_cursor += 28
        if desc_text:
            add_wrapped_text(self, "说明：" + desc_text, 18, y_cursor, self.WIDTH - 36, "#8f9db2", 8)
            y_cursor += 34
        if port_groups:
            heading = QGraphicsSimpleTextItem("接口", self)
            heading.setBrush(QBrush(QColor("#dce7ff")))
            heading.setFont(QFont("Sans", 8, bold_weight))
            heading.setPos(18, y_cursor + 2)
            y_cursor += 22
            for direction, ports in port_groups:
                for port_name in ports:
                    chip = QGraphicsRectItem(18, y_cursor, self.WIDTH - 36, 18, self)
                    chip.setBrush(QBrush(QColor("#182033")))
                    chip.setPen(QPen(QColor("#2f3a52"), 1))
                    chip_text = QGraphicsSimpleTextItem(f"{direction}  {port_name}", self)
                    chip_text.setBrush(QBrush(QColor("#c7d4e8")))
                    chip_text.setFont(QFont("Sans", 8))
                    chip_text.setPos(28, y_cursor + 1)
                    y_cursor += 24
        separator = QGraphicsRectItem(14, self.port_start_y - 10, self.WIDTH - 28, 1, self)
        separator.setBrush(QBrush(QColor("#30394b")))
        separator.setPen(QPen(QColor("#30394b"), 0))
        self.ports: list[PortItem] = []
        rules = PORT_RULES.get(node.get("type"), {})
        for idx, port_type in enumerate(rules.get("in", [])):
            self.ports.append(PortItem(self, "in", port_type, idx))
        for idx, port_type in enumerate(rules.get("out", [])):
            self.ports.append(PortItem(self, "out", port_type, idx))

    def itemChange(self, change, value):
        try:
            position_changed = QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        except AttributeError:
            position_changed = QGraphicsItem.ItemPositionHasChanged
        if change == position_changed:
            self.editor.update_node_position(self.node.get("id"), value)
            self.editor.refresh_edges()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.editor.select_node(self.node.get("id"))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        page = page_for_node(self.node)
        if page:
            self.editor.open_page(page)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TemplatePalette(QListWidget):
    def __init__(self, editor: "VisualEditorWindow"):
        super().__init__()
        self.editor = editor
        self.setDragEnabled(True)

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if not item:
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        template_key = item.data(role)
        if template_key not in NODE_TEMPLATES:
            return
        mime = QMimeData()
        mime.setText(f"efw-template:{template_key}")
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class BlueprintView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, editor: "VisualEditorWindow"):
        super().__init__(scene)
        self.editor = editor
        self.setAcceptDrops(True)
        self.zoom_level = 1.0

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        if modifiers & ctrl:
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else event.delta()
            self.editor.zoom_relation_view(1.12 if delta > 0 else 1 / 1.12)
            event.accept()
            return
        super().wheelEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().text().startswith("efw-template:"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().text().startswith("efw-template:"):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("efw-template:"):
            template_key = text.split(":", 1)[1]
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.editor.add_card_from_template(template_key, self.mapToScene(pos))
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class VisualEditorWindow(QMainWindow):
    def __init__(self, embedded: bool = False):
        super().__init__()
        self.embedded = embedded
        self.setWindowTitle(f"EFW 项目装配器 ({QT_LIB})")
        self.resize(1180, 720)
        self.setMinimumSize(900, 560)
        self.graph_path: Path | None = None
        self.current_node_id: str | None = None
        self.current_code_index: int | None = None
        self.node_items: dict[str, GraphNodeItem] = {}
        self.edge_items: list[QGraphicsLineItem] = []
        self.drag_line: QGraphicsLineItem | None = None
        self.drag_port: PortItem | None = None
        self.validation_messages: list[str] = []
        self.validation_targets: list[str | None] = []
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self._suspend_history = False
        self.autosave_path = REPO_ROOT / ".efw_studio_autosave.json"
        self.open_pages = [root_page()]
        self.active_page_key = "root"
        self.graph = self.default_graph()
        self.setStyleSheet(WORKBENCH_STYLESHEET)
        self._build_ui()
        self._install_shortcuts()
        self.refresh_all()

    def graph_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.graph)

    def push_undo(self) -> None:
        if self._suspend_history:
            return
        self.undo_stack.append(self.graph_snapshot())
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(self.graph_snapshot())
        self.graph = self.undo_stack.pop()
        self.current_node_id = None
        self.refresh_all()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(self.graph_snapshot())
        self.graph = self.redo_stack.pop()
        self.current_node_id = None
        self.refresh_all()

    def autosave_graph(self) -> None:
        try:
            self.autosave_path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            return

    def refresh_after_change(self) -> None:
        self.autosave_graph()
        self.refresh_all()

    def _install_shortcuts(self) -> None:
        shortcuts = {
            "Ctrl+N": self.new_graph,
            "Ctrl+O": self.open_graph,
            "Ctrl+S": self.save_graph,
            "Ctrl+Shift+S": self.save_graph_as,
            "Ctrl+Z": self.undo,
            "Ctrl+Y": self.redo,
            "Ctrl+G": self.generate_application,
            "Ctrl+M": self.add_selected_card,
            "Delete": self.delete_selected_node,
            "Backspace": self.delete_selected_node,
            "Ctrl++": lambda: self.zoom_relation_view(1.15),
            "Ctrl+=": lambda: self.zoom_relation_view(1.15),
            "Ctrl+-": lambda: self.zoom_relation_view(1 / 1.15),
            "Ctrl+0": self.reset_relation_zoom,
            "Ctrl+1": lambda: self.set_workspace("项目总览"),
            "Ctrl+2": lambda: self.set_workspace("模块装配"),
            "Ctrl+3": lambda: self.set_workspace("关系视图"),
            "Ctrl+4": lambda: self.set_workspace("生成发布"),
            "Alt+1": lambda: self.set_right_tab("项目结构"),
            "Alt+2": lambda: self.set_right_tab("属性表单"),
            "Alt+3": lambda: self.set_right_tab("代码"),
            "Alt+4": lambda: self.set_right_tab("实时校验"),
            "F5": self.validate_current_graph,
            "Esc": self.exit_module,
        }
        self.shortcuts: list[Any] = []
        for sequence, callback in shortcuts.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def default_graph(self) -> dict[str, Any]:
        return {
            "project": {"name": "generated_generic_embedded_app", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {**copy.deepcopy(NODE_TEMPLATES["project.module"]), "id": "system_core", "display_name": "系统核心"},
                {**copy.deepcopy(NODE_TEMPLATES["hal.custom"]), "module": "system_core"},
                {**copy.deepcopy(NODE_TEMPLATES["sensor.custom"]), "id": "battery_sensor", "module": "system_core", "hal_name": "uart_debug", "read": "app_battery_sensor_read"},
                {**copy.deepcopy(NODE_TEMPLATES["actuator.custom"]), "module": "system_core"},
                {**copy.deepcopy(NODE_TEMPLATES["module.custom"]), "id": "health_service", "module": "system_core", "module_type": "EFW_MODULE_SERVICE"},
                {**copy.deepcopy(NODE_TEMPLATES["event.topic"]), "module": "system_core"},
                {**copy.deepcopy(NODE_TEMPLATES["event.subscriber"]), "module": "system_core", "target": "health_service"},
                {**copy.deepcopy(NODE_TEMPLATES["task.periodic"]), "id": "heartbeat_100ms", "module": "system_core", "period_ms": 100, "call": "app_heartbeat_100ms"},
            ],
            "flows": [],
            "edges": [
                {"id": "edge_system_uart", "from": "system_core", "to": "uart_debug", "from_port": "group", "to_port": "node", "kind": "contains"},
                {"id": "edge_topic_subscriber", "from": "topic_battery", "to": "subscribe_battery", "from_port": "topic", "to_port": "topic", "kind": "event"},
            ],
            "tasks": [
                {"id": "battery_sample_20ms", "type": "task.periodic", "period_ms": 20, "call": "app_battery_sample_20ms"},
            ],
            "custom_files": [
                {"path": "app_custom.c", "content": DEFAULT_CUSTOM_C},
            ],
            "ui": {
                "positions": {
                    "system_core": [20, 20],
                    "uart_debug": [20, 130],
                    "battery_sensor": [250, 120],
                    "status_led": [250, 240],
                    "health_service": [500, 120],
                    "topic_battery": [500, 240],
                    "subscribe_battery": [740, 240],
                    "heartbeat_100ms": [740, 120],
                }
            },
        }

    def _build_ui(self) -> None:
        if not self.embedded:
            toolbar = QToolBar("项目工具栏")
            self.addToolBar(toolbar)
            toolbar.addAction("新建", self.new_graph)
            toolbar.addAction("项目向导", self.project_wizard)
            toolbar.addAction("打开", self.open_graph)
            toolbar.addAction("保存", self.save_graph)
            toolbar.addAction("另存为", self.save_graph_as)
            toolbar.addAction("撤销", self.undo)
            toolbar.addAction("重做", self.redo)
            toolbar.addAction("校验", self.validate_current_graph)
            toolbar.addAction("生成", self.generate_application)
            toolbar.addAction("快捷键", self.show_shortcuts)

        root_splitter = QSplitter()
        self.setCentralWidget(root_splitter)

        left = QWidget()
        left.setObjectName("NavRail")
        left.setMinimumWidth(180)
        left.setMaximumWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        title = QLabel("EFW")
        title.setStyleSheet("font-size: 18pt; font-weight: 700; color: #ffffff;")
        left_layout.addWidget(title)
        left_layout.addWidget(QLabel("Project Builder"))
        self.workflow_list = QListWidget()
        workflow_steps = [
            ("项目总览", "dashboard"),
            ("模块装配", "assembly"),
            ("资源规划", "resources"),
            ("关系视图", "relations"),
            ("代码补齐", "code"),
            ("生成发布", "release"),
        ]
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        for label, key in workflow_steps:
            item = QListWidgetItem(label, self.workflow_list)
            item.setData(role, key)
        self.workflow_list.itemClicked.connect(self.switch_workflow_item)
        left_layout.addWidget(self.workflow_list)
        self.workflow_hint = QLabel("当前项目：从总览进入，按模块装配组件，最后校验生成。")
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setStyleSheet("background: #151a24; border: 1px solid #242936; border-radius: 12px; padding: 10px; color: #b8c3d8;")
        left_layout.addWidget(self.workflow_hint)
        current_container_btn = QPushButton("进入选中对象")
        current_container_btn.clicked.connect(self.open_selected_container)
        left_layout.addWidget(current_container_btn)

        self.palette_label = QLabel("快速添加")
        left_layout.addWidget(self.palette_label)
        self.palette = TemplatePalette(self)
        self.palette.itemDoubleClicked.connect(lambda _item: self.add_selected_card())
        for category, node_types in NODE_CATEGORIES:
            header = QListWidgetItem(f"▾ {category}", self.palette)
            header.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, "__category__")
            header.setBackground(QBrush(QColor("#233544")))
            header.setForeground(QBrush(QColor("#ffecb3")))
            for node_type in node_types:
                template_type = NODE_TEMPLATES.get(node_type, {}).get("type", node_type)
                item = QListWidgetItem(f"  {display_label(node_type)}  ({template_type})", self.palette)
                item.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, node_type)
                theme = node_theme(template_type)
                item.setBackground(QBrush(QColor(theme["bg"])))
                item.setForeground(QBrush(QColor("#f4fbff")))
        left_layout.addWidget(self.palette)
        add_btn = QPushButton("添加到当前页面")
        add_btn.clicked.connect(self.add_selected_card)
        left_layout.addWidget(add_btn)
        root_splitter.addWidget(left)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setMinimumWidth(360)
        self.workspace_tabs.addTab(self._build_dashboard_tab(), "项目总览")
        self.workspace_tabs.addTab(self._build_assembly_tab(), "模块装配")

        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        self.page_tabs = QTabBar()
        self.page_tabs.setExpanding(False)
        self.page_tabs.setTabsClosable(True)
        self.page_tabs.currentChanged.connect(self.switch_page_tab)
        self.page_tabs.tabCloseRequested.connect(self.close_page_tab)
        canvas_layout.addWidget(self.page_tabs)
        page_controls = QHBoxLayout()
        page_controls.addWidget(QLabel("关系视图：用页面标签进入模块/状态机/Topic；连线从输出端口拖到输入端口。"))
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.clicked.connect(lambda: self.zoom_relation_view(1 / 1.15))
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.clicked.connect(lambda: self.zoom_relation_view(1.15))
        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.clicked.connect(self.reset_relation_zoom)
        root_btn = QPushButton("返回根项目")
        root_btn.clicked.connect(self.exit_module)
        page_controls.addWidget(zoom_out_btn)
        page_controls.addWidget(zoom_in_btn)
        page_controls.addWidget(zoom_reset_btn)
        page_controls.addWidget(root_btn)
        canvas_layout.addLayout(page_controls)
        self.module_scope_label = QLabel("当前视图：根项目")
        canvas_layout.addWidget(self.module_scope_label)
        self.scene = QGraphicsScene()
        self.view = BlueprintView(self.scene, self)
        canvas_layout.addWidget(self.view)
        self.workspace_tabs.addTab(canvas, "关系视图")
        self.workspace_tabs.addTab(self._build_release_tab(), "生成发布")
        root_splitter.addWidget(self.workspace_tabs)

        inspector = QWidget()
        inspector.setMinimumWidth(260)
        inspector.setMaximumWidth(720)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        inspector_title = QLabel("Inspector")
        inspector_title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #ffffff;")
        inspector_layout.addWidget(inspector_title)
        self.inspector_nav = QListWidget()
        inspector_layout.addWidget(self.inspector_nav)
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self._build_structure_tab(), "项目结构")
        self.right_tabs.addTab(self._build_properties_tab(), "属性表单")
        self.right_tabs.addTab(self._build_code_tab(), "代码")
        self.right_tabs.addTab(self._build_validation_tab(), "实时校验")
        self.right_tabs.addTab(self._build_mapping_tab(), "生成映射")
        self.right_tabs.addTab(self._build_file_tree_tab(), "文件树预览")
        self.right_tabs.addTab(self._build_schedule_tab(), "任务调度")
        self.right_tabs.addTab(self._build_pin_planner_tab(), "Board Profile / Pin Planner")
        self.right_tabs.addTab(self._build_json_tab(), "Graph JSON")
        for index in range(self.right_tabs.count()):
            item = QListWidgetItem(self.right_tabs.tabText(index), self.inspector_nav)
            item.setData(role, index)
        self.inspector_nav.currentRowChanged.connect(self.switch_inspector_panel)
        self.inspector_nav.setCurrentRow(0)
        self.right_tabs.tabBar().hide()
        inspector_layout.addWidget(self.right_tabs, 1)
        root_splitter.addWidget(inspector)
        root_splitter.setChildrenCollapsible(True)
        root_splitter.setSizes([210, 620, 320])

    def switch_inspector_panel(self, row: int) -> None:
        if hasattr(self, "right_tabs") and 0 <= row < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(row)

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("项目总览：先看项目状态，再进入模块装配或生成发布。"))
        self.dashboard_output = QPlainTextEdit()
        self.dashboard_output.setReadOnly(True)
        layout.addWidget(self.dashboard_output)
        buttons = QHBoxLayout()
        for text, callback in [
            ("进入模块装配", lambda: self.set_workspace("模块装配")),
            ("校验项目", self.validate_current_graph),
            ("生成发布", lambda: self.set_workspace("生成发布")),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return widget

    def _build_assembly_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("模块装配：以模块为单位组织 HAL / Sensor / Actuator / Algorithm / Task / Event / State。"))
        self.module_list = QListWidget()
        self.module_list.itemClicked.connect(self.open_module_item)
        layout.addWidget(self.module_list)
        buttons = QHBoxLayout()
        add_module_btn = QPushButton("新增模块")
        add_module_btn.clicked.connect(self.add_project_module)
        open_module_btn = QPushButton("进入模块")
        open_module_btn.clicked.connect(self.open_selected_module_from_list)
        relation_btn = QPushButton("查看关系")
        relation_btn.clicked.connect(lambda: self.set_workspace("关系视图"))
        buttons.addWidget(add_module_btn)
        buttons.addWidget(open_module_btn)
        buttons.addWidget(relation_btn)
        layout.addLayout(buttons)
        return widget

    def _build_release_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("生成发布：把校验、缺失回调、资源冲突和生成预览汇总成清单。"))
        self.release_output = QPlainTextEdit()
        self.release_output.setReadOnly(True)
        layout.addWidget(self.release_output)
        buttons = QHBoxLayout()
        validate_btn = QPushButton("刷新检查")
        validate_btn.clicked.connect(lambda: self.refresh_validation_panel(show_dialog=False))
        generate_btn = QPushButton("生成 application")
        generate_btn.clicked.connect(self.generate_application)
        buttons.addWidget(validate_btn)
        buttons.addWidget(generate_btn)
        layout.addLayout(buttons)
        return widget

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.selected_label = QLabel("未选择卡片")
        layout.addWidget(self.selected_label)
        self.ports_label = QLabel("端口：未选择")
        self.ports_label.setWordWrap(True)
        layout.addWidget(self.ports_label)
        self.property_table = QTableWidget(0, 4)
        self.property_table.setHorizontalHeaderLabels(["属性", "值", "控件类型", "契约"])
        self.property_table.setMinimumHeight(120)
        layout.addWidget(self.property_table)
        apply_form_btn = QPushButton("应用表单")
        apply_form_btn.clicked.connect(self.apply_property_form)
        layout.addWidget(apply_form_btn)
        layout.addWidget(QLabel("当前卡片回调实现："))
        callback_row = QHBoxLayout()
        self.callback_select = QComboBox()
        self.callback_select.currentTextChanged.connect(self.load_selected_callback_implementation)
        save_callback_btn = QPushButton("保存到 app_custom.c")
        save_callback_btn.clicked.connect(self.save_selected_callback_implementation)
        open_code_btn = QPushButton("打开代码页")
        open_code_btn.clicked.connect(lambda: self.set_right_tab("代码"))
        callback_row.addWidget(self.callback_select)
        callback_row.addWidget(save_callback_btn)
        callback_row.addWidget(open_code_btn)
        layout.addLayout(callback_row)
        self.callback_preview_output = QPlainTextEdit()
        self.callback_preview_output.setMaximumHeight(180)
        self.callback_preview_output.setFont(QFont("Consolas", 9))
        layout.addWidget(self.callback_preview_output)
        layout.addWidget(QLabel("高级 JSON（复杂数组/对象可在这里编辑）"))
        self.node_json_editor = QPlainTextEdit()
        self.node_json_editor.setMaximumHeight(150)
        layout.addWidget(self.node_json_editor)
        apply_btn = QPushButton("应用 JSON")
        apply_btn.clicked.connect(self.apply_node_json)
        delete_btn = QPushButton("删除卡片")
        delete_btn.clicked.connect(self.delete_selected_node)
        layout.addWidget(apply_btn)
        layout.addWidget(delete_btn)
        return widget

    def _build_pin_planner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Board Profile 与 Pin Planner：只做资源规划和冲突检查，会写回 Graph/app_board_config.h；不会自动生成 STM32 HAL、ESP-IDF 或 DriverLib 调用。真实硬件代码请放入 board_adapters。"))
        self.board_profile_edit = QComboBox()
        self.board_profile_edit.addItems(list(BOARD_PROFILES))
        layout.addWidget(self.board_profile_edit)
        profile_btn = QPushButton("套用 Board Profile 默认资源")
        profile_btn.clicked.connect(self.apply_board_profile_defaults)
        layout.addWidget(profile_btn)
        self.pin_table = QTableWidget(0, 5)
        self.pin_table.setHorizontalHeaderLabels(["节点", "用途", "端口/定时器", "引脚/通道", "备注"])
        layout.addWidget(self.pin_table)
        apply_btn = QPushButton("应用 Pin Planner")
        apply_btn.clicked.connect(self.apply_pin_planner)
        layout.addWidget(apply_btn)
        return widget

    def _build_validation_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("校验错误列表（点击可定位到相关卡片）："))
        self.validation_list = QListWidget()
        self.validation_list.itemClicked.connect(self.open_validation_item)
        layout.addWidget(self.validation_list)
        self.validation_output = QPlainTextEdit()
        self.validation_output.setReadOnly(True)
        layout.addWidget(self.validation_output)
        run_btn = QPushButton("立即校验")
        run_btn.clicked.connect(self.validate_current_graph)
        layout.addWidget(run_btn)
        return widget

    def _build_mapping_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.mapping_output = QPlainTextEdit()
        self.mapping_output.setReadOnly(True)
        layout.addWidget(self.mapping_output)
        return widget

    def _build_structure_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.structure_output = QPlainTextEdit()
        self.structure_output.setReadOnly(True)
        layout.addWidget(self.structure_output)
        return widget

    def _build_file_tree_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.file_tree_output = QPlainTextEdit()
        self.file_tree_output.setReadOnly(True)
        layout.addWidget(self.file_tree_output)
        return widget

    def _build_schedule_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.schedule_output = QPlainTextEdit()
        self.schedule_output.setReadOnly(True)
        layout.addWidget(self.schedule_output)
        return widget

    def shortcuts_text(self) -> str:
        return """快捷键
Ctrl+N    新建 Graph
Ctrl+O    打开 Graph
Ctrl+S    保存 Graph
Ctrl+Shift+S  另存为 Graph
Ctrl+Z    撤销
Ctrl+Y    重做
Ctrl+G    生成 application
Ctrl+M    添加当前选中的模板卡片
Delete / Backspace 删除当前卡片
Ctrl++ / Ctrl+- 关系视图缩放
Ctrl+0    关系视图恢复 100%
Ctrl+1..4 快速切换：总览 / 模块装配 / 关系视图 / 生成发布
Alt+1..4  快速切换 Inspector：项目结构 / 属性 / 代码 / 校验
F5        实时校验
Esc       返回根项目页面

当前阶段先固定快捷键，避免设置项和项目文件格式过早复杂化；如果后续用户频繁冲突，再加入可配置快捷键。"""

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "快捷键", self.shortcuts_text())

    def _build_code_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        header = QHBoxLayout()
        title = QLabel("Code Workspace")
        title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #ffffff;")
        self.code_status_label = QLabel("未选择文件")
        self.code_status_label.setStyleSheet("color: #8f9db2;")
        header.addWidget(title)
        header.addWidget(self.code_status_label)
        layout.addLayout(header)
        row = QHBoxLayout()
        self.code_files = QListWidget()
        self.code_files.setMaximumWidth(120)
        self.code_files.currentRowChanged.connect(self.select_code_file)
        row.addWidget(self.code_files, 1)
        self.code_editor = QPlainTextEdit()
        self.code_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if hasattr(QPlainTextEdit, "LineWrapMode") else QPlainTextEdit.NoWrap)
        code_font = QFont("Consolas", 10)
        self.code_editor.setFont(code_font)
        self.code_editor.setTabStopDistance(QFontMetrics(code_font).horizontalAdvance("  "))
        self.code_editor.setStyleSheet("background: #0b1020; color: #dce7ff; border: 1px solid #242936; border-radius: 12px; padding: 10px;")
        row.addWidget(self.code_editor, 3)
        layout.addLayout(row)
        controls = QHBoxLayout()
        add_btn = QPushButton("新建文件")
        add_btn.clicked.connect(self.add_code_file)
        apply_btn = QPushButton("保存代码")
        apply_btn.clicked.connect(self.apply_code_file)
        delete_btn = QPushButton("删除文件")
        delete_btn.clicked.connect(self.delete_code_file)
        format_btn = QPushButton("简单格式化")
        format_btn.clicked.connect(self.format_code_file)
        stub_btn = QPushButton("一键生成缺失回调")
        stub_btn.clicked.connect(self.generate_missing_callbacks)
        cond_btn = QPushButton("一键创建条件函数")
        cond_btn.clicked.connect(self.generate_condition_callbacks)
        controls.addWidget(add_btn)
        controls.addWidget(apply_btn)
        controls.addWidget(delete_btn)
        controls.addWidget(format_btn)
        controls.addWidget(stub_btn)
        controls.addWidget(cond_btn)
        layout.addLayout(controls)
        layout.addWidget(QLabel("回调补齐清单（来自 codegen 契约）："))
        self.callback_gap_output = QPlainTextEdit()
        self.callback_gap_output.setReadOnly(True)
        layout.addWidget(self.callback_gap_output)
        layout.addWidget(QLabel("Custom code is saved in graph.custom_files and emitted beside generated application files."))
        return widget

    def _build_json_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.graph_json_editor = QPlainTextEdit()
        apply_btn = QPushButton("Apply Full Graph JSON")
        apply_btn.clicked.connect(self.apply_full_json)
        layout.addWidget(self.graph_json_editor)
        layout.addWidget(apply_btn)
        return widget

    def refresh_all(self) -> None:
        self.refresh_open_page_metadata()
        self.refresh_page_tabs()
        self.refresh_scene()
        self.refresh_json_editor()
        self.refresh_code_list()
        self.refresh_pin_planner()
        self.refresh_mapping_view()
        self.refresh_structure_view()
        self.refresh_file_tree_view()
        self.refresh_schedule_view()
        self.refresh_callback_gap_view()
        self.refresh_validation_panel(show_dialog=False)
        self.refresh_dashboard_view()
        self.refresh_module_assembly_view()
        self.refresh_release_view()
        self.refresh_workflow_panel()
        visible_ids = {node.get("id") for node in self.visible_nodes()}
        if self.current_node_id not in visible_ids:
            self.current_node_id = None
        self.select_node(self.current_node_id)

    def set_right_tab(self, title: str) -> None:
        if not hasattr(self, "right_tabs"):
            return
        for index in range(self.right_tabs.count()):
            if self.right_tabs.tabText(index) == title:
                self.right_tabs.setCurrentIndex(index)
                if hasattr(self, "inspector_nav"):
                    self.inspector_nav.setCurrentRow(index)
                return

    def set_workspace(self, title: str) -> None:
        if not hasattr(self, "workspace_tabs"):
            return
        for index in range(self.workspace_tabs.count()):
            if self.workspace_tabs.tabText(index) == title:
                self.workspace_tabs.setCurrentIndex(index)
                return

    def zoom_relation_view(self, factor: float) -> None:
        if not hasattr(self, "view"):
            return
        current = getattr(self.view, "zoom_level", 1.0)
        next_zoom = max(0.35, min(2.5, current * factor))
        factor = next_zoom / current
        self.view.scale(factor, factor)
        self.view.zoom_level = next_zoom

    def reset_relation_zoom(self) -> None:
        if not hasattr(self, "view"):
            return
        self.view.resetTransform()
        self.view.zoom_level = 1.0

    def switch_workflow_item(self, item: QListWidgetItem) -> None:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        step = item.data(role)
        workspace_by_step = {
            "dashboard": "项目总览",
            "assembly": "模块装配",
            "resources": "模块装配",
            "relations": "关系视图",
            "code": "关系视图",
            "release": "生成发布",
        }
        right_by_step = {
            "dashboard": "项目结构",
            "assembly": "属性表单",
            "resources": "Board Profile / Pin Planner",
            "relations": "生成映射",
            "code": "代码",
            "release": "实时校验",
        }
        if step == "release":
            self.refresh_validation_panel(show_dialog=False)
        self.set_workspace(workspace_by_step.get(str(step), "项目总览"))
        self.set_right_tab(right_by_step.get(str(step), "属性表单"))
        self.refresh_workflow_panel()

    def refresh_workflow_panel(self) -> None:
        if not hasattr(self, "workflow_hint"):
            return
        page = self.active_page()
        visible_count = len(self.visible_nodes())
        selected = self.current_node_id or "未选择"
        if page.get("kind") == "root":
            next_step = "双击模块、状态机或 Topic 进入专用页面；根页面只表达顶层结构。"
        elif page.get("kind") == "module":
            next_step = "在这里添加 HAL/Sensor/Algorithm/Actuator/Task，再用端口表达关系。"
        elif page.get("kind") == "state":
            next_step = "添加 State / Transition，填写 condition 后校验。"
        elif page.get("kind") == "comm":
            next_step = "添加 Publisher / Subscriber，业务 publish 写在 Code 页。"
        else:
            next_step = "选择节点后编辑属性，校验通过再生成。"
        self.workflow_hint.setText(f"当前页面：{page_title(page)}\n可见节点：{visible_count}\n当前选择：{selected}\n建议：{next_step}")
        if hasattr(self, "palette_label"):
            self.palette_label.setText(f"当前页面可添加组件：{page_title(page)}")

    def open_selected_container(self) -> None:
        node = self._find_node(self.current_node_id) if self.current_node_id else None
        page = page_for_node(node) if node else None
        if page:
            self.open_page(page)
            return
        QMessageBox.information(self, "打开容器", "请先选择 project.module、state.machine 或 event.topic。普通组件会在当前页面编辑属性。")

    def refresh_dashboard_view(self) -> None:
        if not hasattr(self, "dashboard_output"):
            return
        nodes = self.graph.get("nodes", [])
        modules = [node for node in nodes if node.get("type") == "project.module"]
        topics = [node for node in nodes if node.get("type") == "event.topic"]
        machines = [node for node in nodes if node.get("type") == "state.machine"]
        missing = self.missing_callback_requirements()
        conflicts = self.collect_pin_conflicts()
        errors = [msg for msg in self.validation_messages if msg.startswith("❌")]
        warnings = [msg for msg in self.validation_messages if msg.startswith("⚠️")]
        project = self.graph.get("project", {})
        board = self.graph.get("board", {})
        lines = [
            f"项目：{project.get('name', 'unnamed')}",
            f"tick：{project.get('tick_ms', 1)} ms",
            f"Board Profile：{board.get('profile', project.get('board_profile', 'generic-mock'))}",
            "",
            "装配状态",
            f"- 模块：{len(modules)}",
            f"- 组件：{len([node for node in nodes if node.get('type') != 'project.module'])}",
            f"- Topic：{len(topics)}",
            f"- 状态机：{len(machines)}",
            f"- Flow：{len(self.graph.get('flows', []))}",
            f"- Task：{len(self.graph.get('tasks', [])) + len([node for node in nodes if node.get('type') == 'task.periodic'])}",
            "",
            "发布就绪度",
            f"- 校验错误：{len(errors)}",
            f"- 警告：{len(warnings)}",
            f"- 缺失回调：{len(missing)}",
            f"- Pin 冲突：{len(conflicts)}",
            "",
            "建议路径",
            "1. 到“模块装配”创建模块并添加组件。",
            "2. 到“关系视图”确认模块、Topic、状态机关系。",
            "3. 到“代码补齐”生成缺失回调并补业务逻辑。",
            "4. 到“生成发布”检查清单并生成 application。",
        ]
        self.dashboard_output.setPlainText("\n".join(lines))

    def refresh_module_assembly_view(self) -> None:
        if not hasattr(self, "module_list"):
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        current = self.module_list.currentItem().data(role) if self.module_list.currentItem() else None
        self.module_list.blockSignals(True)
        self.module_list.clear()
        modules = [node for node in self.graph.get("nodes", []) if node.get("type") == "project.module"]
        for module in modules:
            mid = str(module.get("id"))
            children = [node for node in self.graph.get("nodes", []) if node.get("module") == mid or node.get("parent") == mid]
            label = f"{module.get('display_name') or mid} ({mid}) · {len(children)} 个内部节点"
            item = QListWidgetItem(label, self.module_list)
            item.setData(role, mid)
            if mid == current:
                self.module_list.setCurrentItem(item)
        if not modules:
            QListWidgetItem("尚未创建模块。点击“新增模块”开始。", self.module_list)
        self.module_list.blockSignals(False)

    def refresh_release_view(self) -> None:
        if not hasattr(self, "release_output"):
            return
        missing = self.missing_callback_requirements()
        conflicts = self.collect_pin_conflicts()
        errors = [msg for msg in self.validation_messages if msg.startswith("❌")]
        warnings = [msg for msg in self.validation_messages if msg.startswith("⚠️")]
        lines = ["生成发布检查清单", ""]
        checks = [
            (not errors, f"Graph 校验错误：{len(errors)}"),
            (not warnings, f"警告：{len(warnings)}"),
            (not missing, f"缺失回调：{len(missing)}"),
            (not conflicts, f"Pin 冲突：{len(conflicts)}"),
            (bool(self.graph.get("nodes")), "Graph 至少包含一个节点"),
        ]
        for ok, text in checks:
            lines.append(("[OK] " if ok else "[TODO] ") + text)
        if missing:
            lines.append("")
            lines.append("缺失回调：")
            for item in missing[:12]:
                lines.append(f"- {item['owner']}.{item['field']} -> {item['name']}")
        if errors or warnings:
            lines.append("")
            lines.append("校验消息：")
            for message in (errors + warnings)[:12]:
                lines.append(f"- {message}")
        self.release_output.setPlainText("\n".join(lines))

    def open_module_item(self, item: QListWidgetItem) -> None:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        module_id = item.data(role)
        if module_id:
            self.open_node_location(str(module_id))

    def open_selected_module_from_list(self) -> None:
        if not hasattr(self, "module_list"):
            return
        item = self.module_list.currentItem()
        if item:
            self.open_module_item(item)

    def add_project_module(self) -> None:
        base_id = "module"
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        index = 1
        new_id = f"{base_id}_{index}"
        while new_id in existing:
            index += 1
            new_id = f"{base_id}_{index}"
        module = copy.deepcopy(NODE_TEMPLATES["project.module"])
        module["id"] = new_id
        module["display_name"] = f"模块 {index}"
        self.push_undo()
        self.graph.setdefault("nodes", []).append(module)
        self.current_node_id = new_id
        self.refresh_all()
        self.open_node_location(new_id)

    def active_page(self) -> dict[str, str]:
        return next((page for page in self.open_pages if page.get("key") == self.active_page_key), self.open_pages[0])

    def visible_nodes(self) -> list[dict[str, Any]]:
        return visible_nodes_for_page(self.graph, self.active_page())

    def page_source_node(self, page: dict[str, str] | None = None) -> dict[str, Any] | None:
        page = page or self.active_page()
        if page.get("kind") == "root":
            return None
        return self._find_node(page.get("id"))

    def refresh_open_page_metadata(self) -> None:
        refreshed = [root_page()]
        for page in self.open_pages[1:]:
            source = self._find_node(page.get("id"))
            next_page = page_for_node(source) if source else None
            if next_page:
                refreshed.append(next_page)
        self.open_pages = refreshed
        if not any(page.get("key") == self.active_page_key for page in self.open_pages):
            self.active_page_key = "root"

    def open_page(self, page: dict[str, str]) -> None:
        source = self._find_node(page.get("id"))
        refreshed = page_for_node(source) if source else page
        if not any(item.get("key") == refreshed.get("key") for item in self.open_pages):
            self.open_pages.append(refreshed)
        self.active_page_key = refreshed.get("key", "root")
        self.refresh_all()

    def enter_module(self, module_id: str | None) -> None:
        if not module_id:
            return
        node = self._find_node(module_id)
        page = page_for_node(node or {"id": module_id, "type": "project.module"})
        if page:
            self.open_page(page)

    def exit_module(self) -> None:
        self.active_page_key = "root"
        self.refresh_all()

    def switch_page_tab(self, index: int) -> None:
        if 0 <= index < len(self.open_pages):
            self.active_page_key = self.open_pages[index].get("key", "root")
            self.refresh_scene()
            self.refresh_workflow_panel()
            self.select_node(self.current_node_id if self.current_node_id in {node.get("id") for node in self.visible_nodes()} else None)

    def close_page_tab(self, index: int) -> None:
        if index <= 0 or index >= len(self.open_pages):
            return
        closing = self.open_pages[index].get("key")
        del self.open_pages[index]
        if self.active_page_key == closing:
            self.active_page_key = self.open_pages[max(0, index - 1)].get("key", "root")
        self.refresh_all()

    def refresh_page_tabs(self) -> None:
        if not hasattr(self, "page_tabs"):
            return
        self.page_tabs.blockSignals(True)
        try:
            while self.page_tabs.count():
                self.page_tabs.removeTab(0)
            for page in self.open_pages:
                index = self.page_tabs.addTab(page_title(page))
                self.page_tabs.setTabData(index, page.get("key"))
                self.page_tabs.setTabToolTip(index, page_hint(page))
            active_index = next((i for i, page in enumerate(self.open_pages) if page.get("key") == self.active_page_key), 0)
            self.page_tabs.setCurrentIndex(active_index)
            self.page_tabs.setTabEnabled(0, True)
        finally:
            self.page_tabs.blockSignals(False)

    def page_positions(self) -> dict[str, list[float]]:
        ui = self.graph.setdefault("ui", {})
        by_page = ui.setdefault("positions_by_page", {})
        page_key_value = self.active_page().get("key", "root")
        page_positions = by_page.setdefault(page_key_value, {})
        legacy = ui.get("positions", {})
        for node_id, position in legacy.items():
            page_positions.setdefault(node_id, position)
        return page_positions

    def refresh_scene(self) -> None:
        if hasattr(self, "module_scope_label"):
            summary = self.cross_page_edge_summary(self.active_page())
        self.module_scope_label.setText(page_hint(self.active_page()) + ("\n" + summary if summary else ""))
        if self.active_page().get("kind") == "comm":
            topic = self.page_source_node()
            if topic:
                self.select_node(str(topic.get("id")))
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        positions = self.page_positions()
        visible_nodes = self.visible_nodes()
        placed: list[tuple[float, float, float, float]] = []
        for index, node in enumerate(visible_nodes):
            item = GraphNodeItem(node, self)
            pos = positions.get(node.get("id"), [40 + index * 40, 60 + index * 150])
            x = float(pos[0])
            y = float(pos[1])
            while any(not (x + item.WIDTH + 28 < px or x > px + pw + 28 or y + item.HEIGHT + 28 < py or y > py + ph + 28) for px, py, pw, ph in placed):
                y += 34
            placed.append((x, y, item.WIDTH, item.HEIGHT))
            item.setPos(QPointF(x, y))
            self.scene.addItem(item)
            self.node_items[node.get("id")] = item
        self.refresh_edges()

    def cross_page_edge_summary(self, page: dict[str, str]) -> str:
        if page.get("kind") == "root":
            return ""
        visible_ids = {str(node.get("id")) for node in visible_nodes_for_page(self.graph, page)}
        related = []
        for edge in self.graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            src = str(edge.get("from", ""))
            dst = str(edge.get("to", ""))
            if (src in visible_ids) ^ (dst in visible_ids):
                related.append(f"{src} -> {dst} ({edge.get('kind', 'generic')})")
        if not related:
            return "跨页面关系：无"
        preview = "；".join(related[:4])
        suffix = f"；另有 {len(related) - 4} 条" if len(related) > 4 else ""
        return f"跨页面关系：{preview}{suffix}"

    def port_detail_tooltip(self, node: dict[str, Any], direction: str, port_type: str) -> str:
        node_id = str(node.get("id", ""))
        label = PORT_LABELS.get(port_type, port_type)
        desc = PORT_DESCRIPTIONS.get(port_type, label)
        lines = [f"{label} ({port_type})", f"方向: {direction}", desc, ""]
        matches = []
        for edge in self.graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if direction == "out" and edge.get("from") == node_id and edge.get("from_port") == port_type:
                target = self._find_node(str(edge.get("to")))
                effect = edge_effect_description(node, target, edge.get("from_port"), edge.get("to_port")) if target else ""
                matches.append(f"连接到 {edge.get('to')} · {TYPE_LABELS.get(target.get('type'), target.get('type')) if target else 'unknown'} · {edge.get('kind', 'generic')} · {effect}")
            if direction == "in" and edge.get("to") == node_id and edge.get("to_port") == port_type:
                source = self._find_node(str(edge.get("from")))
                effect = edge_effect_description(source, node, edge.get("from_port"), edge.get("to_port")) if source else ""
                matches.append(f"来自 {edge.get('from')} · {TYPE_LABELS.get(source.get('type'), source.get('type')) if source else 'unknown'} · {edge.get('kind', 'generic')} · {effect}")
        if matches:
            lines.append("当前连接：")
            lines.extend(f"- {item}" for item in matches)
        else:
            lines.append("当前未连接。拖到兼容端口即可建立关系。")
        return "\n".join(lines)

    def port_scene_center(self, node_id: str | None, port_type: str | None, direction: str) -> QPointF | None:
        if not node_id or node_id not in self.node_items:
            return None
        item = self.node_items[node_id]
        preferred = [port for port in item.ports if port.direction == direction and (not port_type or port.port_type == port_type)]
        if not preferred:
            preferred = [port for port in item.ports if port.direction == direction]
        if preferred:
            return preferred[0].sceneBoundingRect().center()
        rect = item.sceneBoundingRect()
        if direction == "out":
            return QPointF(rect.right(), rect.center().y())
        return QPointF(rect.left(), rect.center().y())

    def edge_color(self, edge: dict[str, Any]) -> QColor:
        kind = edge.get("kind", "generic")
        by_kind = {
            "contains": "#7e57c2",
            "data_flow": "#42a5f5",
            "hardware_dependency": "#26c6da",
            "schedule": "#5c6bc0",
            "control_flow": "#ec407a",
            "event": "#ff7043",
            "state_transition": "#26a69a",
            "state_transition_from": "#26a69a",
            "state_transition_to": "#80cbc4",
            "code": "#90a4ae",
            "generic": "#78909c",
        }
        return QColor(by_kind.get(str(kind), "#78909c"))

    def edge_pen(self, edge: dict[str, Any]) -> QPen:
        kind = str(edge.get("kind", "generic"))
        width = 3 if kind == "control_flow" else 2
        pen = QPen(self.edge_color(edge), width)
        style_name = {
            "contains": "DashLine",
            "event": "DashDotLine",
            "hardware_dependency": "DotLine",
            "schedule": "DashLine",
            "code": "DotLine",
        }.get(kind)
        if style_name:
            try:
                style = getattr(Qt.PenStyle, style_name)
            except AttributeError:
                style = getattr(Qt, style_name, None)
            if style is not None:
                pen.setStyle(style)
        return pen

    def refresh_edges(self) -> None:
        for edge in self.edge_items:
            self.scene.removeItem(edge)
        self.edge_items = []
        edges: list[dict[str, Any]] = [edge for edge in self.graph.get("edges", []) if isinstance(edge, dict)]
        for flow in self.graph.get("flows", []):
            if flow.get("type") == "control.line_follower":
                sensor = flow.get("sensor")
                sensor_node = self._find_node(sensor)
                edges.extend([
                    {"from": sensor_node.get("input") if sensor_node else self._line_input_id(), "from_port": "hal", "to": sensor, "to_port": "hal", "kind": "hardware_dependency"},
                    {"from": sensor, "from_port": "sensor", "to": flow.get("pid"), "to_port": "sensor", "kind": "data_flow"},
                    {"from": sensor, "from_port": "sensor", "to": flow.get("left_motor"), "to_port": "control", "kind": "control_flow"},
                    {"from": sensor, "from_port": "sensor", "to": flow.get("right_motor"), "to_port": "control", "kind": "control_flow"},
                    {"from": flow.get("pid"), "from_port": "algorithm", "to": flow.get("left_motor"), "to_port": "control", "kind": "control_flow"},
                    {"from": flow.get("pid"), "from_port": "algorithm", "to": flow.get("right_motor"), "to_port": "control", "kind": "control_flow"},
                ])
        for edge in edges:
            src = edge.get("from")
            dst = edge.get("to")
            if src in self.node_items and dst in self.node_items:
                a = self.port_scene_center(src, edge.get("from_port"), "out")
                b = self.port_scene_center(dst, edge.get("to_port"), "in")
                if not a or not b:
                    continue
                line = QGraphicsLineItem()
                line.setLine(a.x(), a.y(), b.x(), b.y())
                line.setPen(self.edge_pen(edge))
                kind_label = EDGE_KIND_LABELS.get(str(edge.get('kind', 'generic')), str(edge.get('kind', 'generic')))
                effect = ""
                src_node = self._find_node(src)
                dst_node = self._find_node(dst)
                if src_node and dst_node:
                    effect = "\n生成/语义：" + edge_effect_description(src_node, dst_node, edge.get('from_port'), edge.get('to_port'))
                tooltip = f"{kind_label}: {src}.{edge.get('from_port', 'out')} → {dst}.{edge.get('to_port', 'in')}{effect}"
                line.setToolTip(tooltip)
                line.setZValue(-1)
                self.scene.addItem(line)
                self.edge_items.append(line)

    def refresh_json_editor(self) -> None:
        self.graph_json_editor.setPlainText(json.dumps(self.graph, ensure_ascii=False, indent=2))
        self.autosave_graph()

    def refresh_code_list(self) -> None:
        self.code_files.blockSignals(True)
        self.code_files.clear()
        for item in self.graph.setdefault("custom_files", []):
            self.code_files.addItem(item.get("path", "unnamed.c"))
        self.code_files.blockSignals(False)
        if self.graph["custom_files"]:
            self.code_files.setCurrentRow(0 if self.current_code_index is None else min(self.current_code_index, len(self.graph["custom_files"]) - 1))
        else:
            self.code_editor.clear()

    def _line_input_id(self) -> str | None:
        for node in self.graph.get("nodes", []):
            if node.get("type") == "hal.gpio_line_input":
                return node.get("id")
        return None

    def node_port_summary(self, node: dict[str, Any]) -> str:
        rules = PORT_RULES.get(node.get("type"), {})
        parts = []
        for direction_label, direction_key in [("输入", "in"), ("输出", "out")]:
            ports = rules.get(direction_key, [])
            if ports:
                labels = [f"{PORT_LABELS.get(port, port)}({port})" for port in ports]
                parts.append(f"{direction_label}: " + ", ".join(labels))
        return "端口：" + ("；".join(parts) if parts else "无")

    def node_contract_summary(self, node: dict[str, Any]) -> str:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        if not contract:
            return "Codegen 契约：未声明"
        generated = ", ".join(contract.get("generated", [])) or "不生成 C 运行代码"
        callbacks = contract.get("callbacks", {})
        callback_parts = []
        for field, signature_key in callbacks.items():
            value = node.get(field)
            if value:
                callback_parts.append(f"{field}={value}: {callback_signature(signature_key)}")
        callback_text = "；回调：" + "；".join(callback_parts) if callback_parts else "；回调：无"
        return f"Codegen：{node_generation_label(str(node.get('type')))}；生成：{generated}{callback_text}；边界：{contract.get('boundary', '')}"

    def node_action_hint(self, node: dict[str, Any]) -> str:
        node_type = str(node.get("type"))
        contract = NODE_CONTRACTS.get(node_type, {})
        if node_type == "processor.custom":
            return "行动：实现 process(ctx, in, out)。当它位于 Sensor → Processor → Algorithm/Actuator 数据流上时，codegen 会生成周期执行链；连接到 project.module 只声明模块接口。"
        if node_type == "event.publisher":
            return "行动：在 custom_files 的 task/module 回调中手写 efw_topic_publish()；该卡片只表达发布关系。"
        if node_type == "project.module":
            return "行动：把节点归属到该模块以整理页面；inputs/outputs 会进入 contract registry 校验，但当前仍不会生成独立 app_xxx_module.c/.h。"
        if node_type == "actuator.motor":
            return "行动：host mock 可编译验证；真实板卡需在板级适配中把 speed/dir 接到 PWM/GPIO。"
        if node_type == "hal.gpio_line_input":
            return "行动：host mock 可设置输入值；真实板卡需把 GPIO/ADC 读取接入板级适配。"
        callbacks = contract.get("callbacks", {})
        active = [field for field in callbacks if node.get(field)]
        if active:
            return "行动：点击 Code 页的一键生成缺失回调，随后在 custom_files/board_adapters 中补真实逻辑。"
        if not contract.get("generated"):
            return "行动：该节点不生成 C 运行代码，仅用于组织或说明。"
        return "行动：检查 Graph 引用和周期，校验通过后即可生成 application。"

    def select_node(self, node_id: str | None) -> None:
        self.current_node_id = node_id
        node = self._find_node(node_id) if node_id else None
        if not node and node_id is None:
            node = self.page_source_node()
            if node:
                self.current_node_id = node.get("id")
        if not node:
            self.selected_label.setText("未选择卡片")
            if hasattr(self, "ports_label"):
                self.ports_label.setText("端口：未选择")
            self.node_json_editor.clear()
            self.property_table.setRowCount(0)
            if hasattr(self, "callback_preview_output"):
                self.callback_preview_output.clear()
            if hasattr(self, "callback_select"):
                self.callback_select.clear()
            return
        prefix = "页面属性" if node.get("id") == self.active_page().get("id") else "已选择"
        self.selected_label.setText(f"{prefix}: {node.get('id')} ({TYPE_LABELS.get(node.get('type'), node.get('type'))})")
        if hasattr(self, "ports_label"):
            self.ports_label.setText(self.node_port_summary(node) + "\n" + self.node_contract_summary(node))
        self.node_json_editor.setPlainText(json.dumps(node, ensure_ascii=False, indent=2))
        self.populate_property_form(node)
        self.refresh_callback_selector(node)

    def page_for_node_location(self, node: dict[str, Any] | None) -> dict[str, str] | None:
        if not node:
            return None
        direct_page = page_for_node(node)
        if direct_page:
            return direct_page
        owner_keys = ("topic", "machine", "module") if node.get("type") in {"event.publisher", "event.subscriber"} else ("module", "machine", "topic")
        for owner_key in owner_keys:
            owner_id = node.get(owner_key)
            if not owner_id:
                continue
            owner = self._find_node(str(owner_id))
            owner_page = page_for_node(owner) if owner else None
            if owner_page:
                return owner_page
        return root_page()

    def open_node_location(self, node_id: str | None) -> None:
        node = self._find_node(str(node_id)) if node_id else None
        page = self.page_for_node_location(node)
        if page:
            self.open_page(page)
        self.select_node(str(node_id) if node_id else None)

    def _find_node(self, node_id: str | None) -> dict[str, Any] | None:
        for node in self.graph.get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None

    def source_files_for_preview(self) -> list[dict[str, str]]:
        return [item for item in self.graph.get("custom_files", []) + self.graph.get("board_adapters", []) if str(item.get("path", "")).endswith((".c", ".h"))]

    def callback_names_for_node(self, node: dict[str, Any]) -> list[str]:
        names = []
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        for field in contract.get("callbacks", {}):
            value = str(node.get(field, "")).strip()
            if value:
                names.append(value)
        if node.get("type") == "task.periodic" and node.get("call"):
            names.append(str(node.get("call")))
        return names

    def find_function_snippet(self, content: str, name: str) -> str | None:
        span = self.find_function_span(content, name)
        if not span:
            return None
        return content[span[0]:span[1]].strip()

    def find_function_span(self, content: str, name: str) -> tuple[int, int] | None:
        marker = content.find(name + "(")
        if marker < 0:
            marker = content.find(name + " (")
        if marker < 0:
            return None
        start = content.rfind("\n", 0, marker) + 1
        brace = content.find("{", marker)
        if brace < 0:
            end = content.find(";", marker)
            return (start, end + 1) if end >= 0 else None
        depth = 0
        for index in range(brace, len(content)):
            if content[index] == "{":
                depth += 1
            elif content[index] == "}":
                depth -= 1
                if depth == 0:
                    return (start, index + 1)
        return (start, len(content))

    def refresh_callback_selector(self, node: dict[str, Any]) -> None:
        if not hasattr(self, "callback_select"):
            return
        self.callback_select.blockSignals(True)
        self.callback_select.clear()
        names = self.callback_names_for_node(node)
        self.callback_select.addItems(names or ["无回调"])
        self.callback_select.blockSignals(False)
        self.load_selected_callback_implementation(self.callback_select.currentText())

    def refresh_callback_preview(self, node: dict[str, Any]) -> None:
        if not hasattr(self, "callback_preview_output"):
            return
        names = self.callback_names_for_node(node)
        if not names:
            self.callback_preview_output.setPlainText("当前卡片没有声明回调函数。")
            return
        chunks = []
        files = self.source_files_for_preview()
        for name in names:
            found = False
            for item in files:
                snippet = self.find_function_snippet(str(item.get("content", "")), name)
                if snippet:
                    chunks.append(f"// {item.get('path')} :: {name}\n{snippet}")
                    found = True
                    break
            if not found:
                chunks.append(f"// 未找到实现：{name}\n// 可到 Code 页点击“一键生成缺失回调”。")
        self.callback_preview_output.setPlainText("\n\n".join(chunks))

    def callback_stub_by_name(self, name: str) -> str:
        for requirement in self.callback_requirements():
            if requirement["name"] == name:
                return self.callback_stub(requirement).strip()
        return f"efw_status_t {name}(void) {{\n  return EFW_OK;\n}}"

    def load_selected_callback_implementation(self, name: str) -> None:
        if not hasattr(self, "callback_preview_output"):
            return
        if not name or name == "无回调":
            self.callback_preview_output.setPlainText("当前卡片没有声明回调函数。")
            return
        for item in self.source_files_for_preview():
            snippet = self.find_function_snippet(str(item.get("content", "")), name)
            if snippet:
                self.callback_preview_output.setPlainText(snippet)
                return
        self.callback_preview_output.setPlainText(self.callback_stub_by_name(name))

    def save_selected_callback_implementation(self) -> None:
        if not hasattr(self, "callback_select") or not hasattr(self, "callback_preview_output"):
            return
        name = self.callback_select.currentText().strip()
        if not name or name == "无回调":
            return
        implementation = self.callback_preview_output.toPlainText().strip() + "\n"
        files = self.graph.setdefault("custom_files", [])
        target = next((item for item in files if item.get("path") == "app_custom.c"), None)
        if target is None:
            target = {"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"}
            files.insert(0, target)
        content = str(target.get("content", ""))
        span = self.find_function_span(content, name)
        self.push_undo()
        if span:
            content = content[:span[0]] + implementation + content[span[1]:]
        else:
            content = content.rstrip() + "\n\n" + implementation
        target["content"] = content
        self.current_code_index = files.index(target)
        self.refresh_code_list()
        self.select_code_file(self.current_code_index)
        self.refresh_json_editor()

    def update_node_position(self, node_id: str | None, pos: QPointF) -> None:
        if not node_id:
            return
        self.page_positions()[node_id] = [round(pos.x(), 1), round(pos.y(), 1)]
        self.refresh_json_editor()

    def apply_page_ownership(self, template: dict[str, Any]) -> bool:
        page = self.active_page()
        kind = page.get("kind")
        owner_id = page.get("id")
        node_type = template.get("type")
        if kind == "root":
            allowed = {"project.module", "event.topic", "event.publisher", "event.subscriber", "custom.card"}
            if node_type not in allowed:
                QMessageBox.warning(self, "不能添加到系统模块视图", "系统模块视图只显示 project.module、模块输入/输出契约和事件发布订阅；请进入模块内部视图后再添加 HAL/Sensor/Processor/Algorithm/Actuator/Task/StateMachine。")
                return False
            if node_type == "custom.card":
                template.setdefault("scope", "root")
            return True
        if kind == "module":
            if node_type == "project.module":
                template["parent"] = owner_id
            elif node_type != "custom.card":
                template["module"] = owner_id
            else:
                template["scope"] = f"module:{owner_id}"
                template["module"] = owner_id
            return True
        if kind == "state":
            allowed = {"state.state", "state.transition"}
            if node_type not in allowed:
                QMessageBox.warning(self, "页面类型不匹配", "状态机页面只允许添加 State / Transition；说明卡片请放在模块或根页面。")
                return False
            template["machine"] = owner_id
            return True
        if kind == "comm":
            allowed = {"event.publisher", "event.subscriber", "custom.card"}
            if node_type not in allowed:
                QMessageBox.warning(self, "页面类型不匹配", "通信页面只建议添加 Publisher / Subscriber / 说明卡片。")
                return False
            if node_type != "custom.card":
                template["topic"] = owner_id
            else:
                template["scope"] = f"comm:{owner_id}"
            return True
        return True

    def add_selected_card(self) -> None:
        item = self.palette.currentItem()
        if not item:
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        node_type = item.data(role)
        self.add_card_from_template(str(node_type))

    def add_card_from_template(self, node_type: str, scene_pos: QPointF | None = None) -> None:
        if node_type not in NODE_TEMPLATES:
            return
        template = copy.deepcopy(NODE_TEMPLATES[node_type])
        if not self.apply_page_ownership(template):
            return
        base_id = template["id"]
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        suffix = 1
        new_id = base_id
        while new_id in existing:
            suffix += 1
            new_id = f"{base_id}_{suffix}"
        template["id"] = new_id
        self.push_undo()
        self.graph.setdefault("nodes", []).append(template)
        if scene_pos is None:
            scene_pos = QPointF(80, 80)
        self.page_positions()[new_id] = [round(scene_pos.x(), 1), round(scene_pos.y(), 1)]
        self.current_node_id = new_id
        self.refresh_all()



    def update_open_pages_after_rename(self, old_id: str, new_id: str) -> None:
        old_keys = {page_key(kind, old_id) for kind in ["module", "state", "comm"]}
        key_map = {page_key(kind, old_id): page_key(kind, new_id) for kind in ["module", "state", "comm"]}
        positions_by_page = self.graph.setdefault("ui", {}).setdefault("positions_by_page", {})
        for old_key, new_key in key_map.items():
            if old_key in positions_by_page and new_key not in positions_by_page:
                positions_by_page[new_key] = positions_by_page.pop(old_key)
        for page in self.open_pages:
            if page.get("id") == old_id:
                kind = page.get("kind", "root")
                page["id"] = new_id
                page["key"] = page_key(kind, new_id)
        if self.active_page_key in old_keys:
            active = next((page for page in self.open_pages if page.get("id") == new_id), None)
            self.active_page_key = active.get("key", "root") if active else "root"

    def rename_node_references(self, old_id: str, new_id: str) -> None:
        if not old_id or not new_id or old_id == new_id:
            return
        reference_keys = {
            "module", "parent", "machine", "from", "to", "topic", "source", "target",
            "input", "hal_name", "comm_name", "sensor", "pid", "left_motor", "right_motor", "flow",
        }
        for node in self.graph.get("nodes", []):
            for key in reference_keys:
                if node.get(key) == old_id:
                    node[key] = new_id
        for edge in self.graph.get("edges", []):
            if edge.get("from") == old_id:
                edge["from"] = new_id
            if edge.get("to") == old_id:
                edge["to"] = new_id
        for flow in self.graph.get("flows", []):
            for key in reference_keys:
                if flow.get(key) == old_id:
                    flow[key] = new_id
        for task in self.graph.get("tasks", []):
            if task.get("flow") == old_id:
                task["flow"] = new_id
        ui = self.graph.setdefault("ui", {})
        positions = ui.setdefault("positions", {})
        if old_id in positions:
            positions[new_id] = positions.pop(old_id)
        for page_positions in ui.setdefault("positions_by_page", {}).values():
            if old_id in page_positions:
                page_positions[new_id] = page_positions.pop(old_id)
        self.update_open_pages_after_rename(old_id, new_id)

    def property_choices(self, node: dict[str, Any], key: str) -> list[str]:
        return core_property_choices(self.graph, node, key, NODE_TEMPLATES)

    def property_widget_kind(self, node: dict[str, Any], key: str, value: Any, choices: list[str]) -> str:
        if choices:
            return "下拉选择"
        if isinstance(value, bool) or key in {"binary_mode", "anti_windup", "enabled"}:
            return "布尔开关"
        if isinstance(value, int) and not isinstance(value, bool) or key.endswith("_ms") or key in {"priority", "period_ms", "channels", "topic_id", "max_iterations"}:
            return "整数"
        if isinstance(value, float) or key in {"kp", "ki", "kd", "out_min", "out_max", "base_speed", "min_speed", "max_speed", "dt"}:
            return "浮点数"
        if node.get("type") == "state.transition" and key == "condition":
            return "必填条件函数"
        if isinstance(value, (dict, list)):
            return "JSON"
        return "文本"

    def property_contract_role(self, node: dict[str, Any], key: str) -> str:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        if key in {"name", "display_name", "description"}:
            return "显示"
        if key == "id":
            return "主键"
        if key in {"input_type", "output_type", "payload_type", "data_type", "output_desc"}:
            return "数据契约"
        callbacks = contract.get("callbacks", {})
        if key in callbacks:
            return "回调"
        if key in contract.get("required", []):
            return "必填"
        if key in contract.get("required_any", []):
            return "至少一项"
        if key in {"module", "parent", "machine", "from", "to", "topic", "source", "target", "input", "hal_name", "comm_name", "sensor", "pid", "left_motor", "right_motor", "flow", "initial"}:
            return "引用"
        if key in contract.get("optional", []):
            return "可选"
        return "扩展"

    def property_issue(self, node: dict[str, Any], key: str, value: Any, choices: list[str]) -> str | None:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        if key in contract.get("required", []) and value in (None, "", []):
            return "必填字段为空"
        required_any = contract.get("required_any", [])
        if key in required_any and not any(node.get(field) not in (None, "", []) for field in required_any):
            return "至少填写其中一个：" + ", ".join(required_any)
        if node.get("type") == "state.transition" and key == "condition" and not str(value).strip():
            return "transition 必须填写条件函数名"
        if choices and value not in (None, "") and str(value) not in {str(item) for item in choices}:
            return "当前引用/枚举值不在可选列表中"
        return None

    def populate_property_form(self, node: dict[str, Any]) -> None:
        self.property_table.setRowCount(0)
        ordered_keys = ["id", "type", "name", "description"]
        ordered_keys.extend(key for key in PROPERTY_FIELD_ORDER.get(str(node.get("type")), []) if key not in ordered_keys)
        ordered_keys.extend(key for key in node if key not in ordered_keys)
        for key in ordered_keys:
            value = node.get(key, "")
            row = self.property_table.rowCount()
            self.property_table.insertRow(row)
            choices = self.property_choices(node, str(key))
            kind = self.property_widget_kind(node, str(key), value, choices)
            issue = self.property_issue(node, str(key), value, choices)
            role = self.property_contract_role(node, str(key))
            key_item = QTableWidgetItem(str(key))
            if issue:
                key_item.setBackground(QBrush(QColor("#5b1f24")))
                key_item.setForeground(QBrush(QColor("#ffb3b3")))
                key_item.setToolTip(issue)
            self.property_table.setItem(row, 0, key_item)
            if choices:
                combo = QComboBox()
                combo.addItems([str(item) for item in choices])
                if str(value) not in [str(item) for item in choices]:
                    combo.addItem(str(value))
                combo.setCurrentText(str(value))
                if issue:
                    combo.setToolTip(issue)
                self.property_table.setCellWidget(row, 1, combo)
            elif kind == "布尔开关":
                check = QCheckBox()
                check.setChecked(bool(value) if not isinstance(value, str) else value.lower() in {"1", "true", "yes", "on"})
                if issue:
                    check.setToolTip(issue)
                self.property_table.setCellWidget(row, 1, check)
            else:
                item = QTableWidgetItem(form_value_text(value))
                if issue:
                    item.setBackground(QBrush(QColor("#5b1f24")))
                    item.setForeground(QBrush(QColor("#ffb3b3")))
                    item.setToolTip(issue)
                    if node.get("type") == "state.transition" and key == "condition" and not str(value).strip():
                        item.setText("<必填：条件函数名>")
                self.property_table.setItem(row, 1, item)
            type_item = QTableWidgetItem(kind)
            if issue:
                type_item.setBackground(QBrush(QColor("#5b1f24")))
                type_item.setForeground(QBrush(QColor("#ffb3b3")))
                type_item.setToolTip(issue)
            self.property_table.setItem(row, 2, type_item)
            role_item = QTableWidgetItem(role)
            role_item.setToolTip(self.property_role_tooltip(node, str(key), role))
            if role in {"必填", "至少一项", "回调"}:
                role_item.setForeground(QBrush(QColor("#ffecb3")))
            elif role == "引用":
                role_item.setForeground(QBrush(QColor("#b3e5fc")))
            elif role in {"显示", "主键", "数据契约"}:
                role_item.setForeground(QBrush(QColor("#c7d4e8")))
            self.property_table.setItem(row, 3, role_item)

    def property_role_tooltip(self, node: dict[str, Any], key: str, role: str) -> str:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        callbacks = contract.get("callbacks", {})
        if key in callbacks:
            return f"用户代码需要实现该回调，签名：{callback_signature(callbacks[key])}"
        if key == "id":
            return "卡片主键。用于连线、页面、归属和 codegen 引用；创建时自动分配，修改时必须保持唯一。"
        if role == "数据契约":
            return "Studio 层的数据说明，用来表达输入/输出/payload 是 float、int、struct、enum 或自定义类型。"
        if role == "必填":
            return "Graph contract 要求该字段必须填写。"
        if role == "至少一项":
            return "这一组字段至少填写一个：" + ", ".join(contract.get("required_any", []))
        if role == "引用":
            return "引用其他节点、flow 或资源；推荐使用下拉选择避免拼写错误。"
        if role == "显示":
            return "Studio 展示字段，不影响 EFW/codegen 核心逻辑；用于让项目更容易阅读。"
        if role == "可选":
            return "Graph contract 声明的可选字段。"
        return "扩展/元数据字段；生成器可能只用于说明或 Studio 展示。"

    def sync_derived_node_fields(self, old_node: dict[str, Any], updated: dict[str, Any]) -> None:
        if updated.get("type") != "task.periodic":
            return
        old_period = old_node.get("period_ms")
        new_period = updated.get("period_ms")
        if old_period == new_period or new_period in (None, ""):
            return
        old_id = str(old_node.get("id", "custom_task_10ms"))
        old_call = str(old_node.get("call", "app_custom_task_10ms"))
        old_name = str(old_node.get("name", old_id))
        old_token = f"{old_period}ms"
        new_token = f"{new_period}ms"
        if old_token in old_id:
            updated["id"] = old_id.replace(old_token, new_token)
        if old_token in old_call:
            updated["call"] = old_call.replace(old_token, new_token)
        if old_token in old_name:
            updated["name"] = old_name.replace(old_token, new_token)

    def apply_property_form(self) -> None:
        if not self.current_node_id:
            return
        node = self._find_node(self.current_node_id)
        if not node:
            return
        self.push_undo()
        old_id = str(node.get("id", self.current_node_id))
        updated: dict[str, Any] = {}
        for row in range(self.property_table.rowCount()):
            key_item = self.property_table.item(row, 0)
            value_item = self.property_table.item(row, 1)
            value_widget = self.property_table.cellWidget(row, 1)
            if not key_item:
                continue
            key = key_item.text().strip()
            if not key:
                continue
            if isinstance(value_widget, QComboBox):
                raw_value = value_widget.currentText()
                value = parse_form_value(raw_value)
            elif isinstance(value_widget, QCheckBox):
                value = value_widget.isChecked()
            else:
                raw_value = value_item.text() if value_item else ""
                if raw_value == "<必填：条件函数名>":
                    raw_value = ""
                value = parse_form_value(raw_value)
            updated[key] = value
        new_id = str(updated.get("id", old_id))
        if new_id != c_ident(new_id):
            QMessageBox.warning(self, "ID 无效", "id 必须是合法 C 标识符：只能包含字母、数字、下划线，且不能以数字开头。")
            return
        if any(item is not node and item.get("id") == new_id for item in self.graph.get("nodes", [])):
            QMessageBox.warning(self, "ID 重复", f"已经存在 id={new_id} 的卡片，请换一个唯一 id。")
            return
        self.sync_derived_node_fields(node, updated)
        new_id = str(updated.get("id", old_id))
        if new_id != c_ident(new_id):
            QMessageBox.warning(self, "ID 无效", "id 必须是合法 C 标识符：只能包含字母、数字、下划线，且不能以数字开头。")
            return
        if any(item is not node and item.get("id") == new_id for item in self.graph.get("nodes", [])):
            QMessageBox.warning(self, "ID 重复", f"已经存在 id={new_id} 的卡片，请换一个唯一 id。")
            return
        if new_id != old_id:
            self.rename_node_references(old_id, new_id)
        nodes = self.graph.get("nodes", [])
        for idx, item in enumerate(nodes):
            if item.get("id") == old_id or item.get("id") == new_id:
                nodes[idx] = updated
                self.current_node_id = new_id
                break
        self.refresh_all()

    def board_profile(self) -> dict[str, Any]:
        board = self.graph.get("board", {})
        profile = str(board.get("profile") or (self.board_profile_edit.currentText() if hasattr(self, "board_profile_edit") else "generic-mock") or "generic-mock")
        return BOARD_PROFILES.get(profile) or BOARD_PROFILES.get("generic-mock", {})

    def pin_cell_text(self, row: int, col: int) -> str:
        widget = self.pin_table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        item = self.pin_table.item(row, col)
        return item.text().strip() if item else ""

    def refresh_pin_planner(self) -> None:
        if not hasattr(self, "pin_table"):
            return
        board = self.graph.get("board", {})
        if hasattr(self, "board_profile_edit"):
            profile = str(board.get("profile", "generic-mock"))
            if self.board_profile_edit.findText(profile) < 0:
                self.board_profile_edit.addItem(profile)
            self.board_profile_edit.setCurrentText(profile)
        self.pin_table.setRowCount(0)
        for node in self.graph.get("nodes", []):
            if node.get("type") == "hal.gpio_line_input":
                for index, pin in enumerate(node.get("pins", [])):
                    self._add_pin_row(node.get("id", ""), f"GPIO输入[{index}]", pin.get("port", ""), pin.get("pin", ""), "循迹/数字输入")
            elif node.get("type") == "actuator.motor":
                pwm = node.get("pwm", {})
                direction = node.get("dir_pin", {})
                self._add_pin_row(node.get("id", ""), "PWM", pwm.get("timer", ""), pwm.get("channel", ""), "电机速度")
                self._add_pin_row(node.get("id", ""), "DIR", direction.get("port", ""), direction.get("pin", ""), "电机方向")


    def apply_board_profile_defaults(self) -> None:
        self.push_undo()
        profile_name = self.board_profile_edit.currentText().strip() or "generic-mock"
        notes = apply_board_profile_defaults_to_graph(self.graph, BOARD_PROFILES, profile_name)
        conflicts = self.collect_pin_conflicts()
        if conflicts:
            QMessageBox.warning(self, "Pin 冲突", "\n".join(conflicts))
        else:
            QMessageBox.information(self, "Board Profile", "已套用默认资源：\n" + "\n".join(notes[:12]))
        self.refresh_all()

    def _add_combo_cell(self, row: int, col: int, choices: list[Any], value: Any) -> None:
        combo = QComboBox()
        text_choices = [str(item) for item in choices]
        if "" not in text_choices:
            text_choices.insert(0, "")
        combo.addItems(text_choices)
        if str(value) not in text_choices:
            combo.addItem(str(value))
        combo.setCurrentText(str(value))
        self.pin_table.setCellWidget(row, col, combo)

    def _add_pin_row(self, node_id: str, usage: str, port, pin, note: str) -> None:
        row = self.pin_table.rowCount()
        self.pin_table.insertRow(row)
        self.pin_table.setItem(row, 0, QTableWidgetItem(str(node_id)))
        self.pin_table.setItem(row, 1, QTableWidgetItem(str(usage)))
        profile = self.board_profile()
        if usage == "PWM":
            self._add_combo_cell(row, 2, profile.get("timers", []), port)
            self._add_combo_cell(row, 3, profile.get("pwm_channels", []), pin)
        else:
            self._add_combo_cell(row, 2, profile.get("ports", []), port)
            pin_count = int(profile.get("pins_per_port", 0) or 0)
            self._add_combo_cell(row, 3, list(range(pin_count)), pin)
        self.pin_table.setItem(row, 4, QTableWidgetItem(str(note)))

    def apply_pin_planner(self) -> None:
        self.push_undo()
        board = self.graph.setdefault("board", {})
        board["profile"] = self.board_profile_edit.currentText().strip() or "generic-mock"
        grouped: dict[str, list[tuple[str, str, str]]] = {}
        errors: list[str] = []
        for row in range(self.pin_table.rowCount()):
            node_id = self.pin_cell_text(row, 0)
            usage = self.pin_cell_text(row, 1)
            port = self.pin_cell_text(row, 2)
            pin = self.pin_cell_text(row, 3)
            if not node_id or not usage:
                continue
            if not port or not pin:
                errors.append(f"第 {row + 1} 行 {node_id}/{usage} 资源为空，请用下拉框选择端口/引脚。")
                continue
            grouped.setdefault(node_id, []).append((usage, port, pin))
        if errors:
            QMessageBox.warning(self, "Pin Planner 空值", "\n".join(errors))
            return
        pin_plan = []
        for node in self.graph.get("nodes", []):
            rows = grouped.get(node.get("id"), [])
            if node.get("type") == "hal.gpio_line_input":
                pins = []
                for usage, port, pin in rows:
                    pins.append({"port": port.upper(), "pin": int(pin)})
                    pin_plan.append({"node": node.get("id"), "usage": usage, "port": port.upper(), "pin": int(pin)})
                if pins:
                    node["pins"] = pins
                    node["channels"] = len(pins)
            elif node.get("type") == "actuator.motor":
                for usage, port, pin in rows:
                    if usage == "PWM":
                        node["pwm"] = {"timer": int(port), "channel": int(pin)}
                        pin_plan.append({"node": node.get("id"), "usage": usage, "timer": int(port), "channel": int(pin)})
                    elif usage == "DIR":
                        node["dir_pin"] = {"port": port.upper(), "pin": int(pin)}
                        pin_plan.append({"node": node.get("id"), "usage": usage, "port": port.upper(), "pin": int(pin)})
        board["pin_plan"] = pin_plan
        conflicts = self.collect_pin_conflicts()
        if conflicts:
            QMessageBox.warning(self, "Pin 冲突", "\n".join(conflicts))
        self.refresh_all()

    def refresh_mapping_view(self) -> None:
        if not hasattr(self, "mapping_output"):
            return
        lines = ["Graph → Generated Code 映射（来自 codegen 契约）", ""]
        for node in self.graph.get("nodes", []):
            node_type = node.get("type")
            if node_type and node_type.startswith(("hal.", "sensor.", "actuator.")):
                target = "app_platform.c"
            elif node_type and node_type.startswith(("algorithm.", "module.")):
                target = "app_components.c"
            elif node_type == "task.periodic":
                target = "app_bootstrap.c"
            elif node_type and node_type.startswith("event."):
                target = "app_manifest.h / app_bootstrap.c / event bus"
            elif node_type == "project.module":
                target = "Graph 组织分组 / Studio 页面"
            else:
                target = "custom_files / docs"
            contract = NODE_CONTRACTS.get(str(node_type), {})
            status, note = NODE_GENERATION_STATUS.get(node_type, ("未知", "未声明生成能力"))
            generated = ", ".join(contract.get("generated", [])) or "不生成 C 运行代码"
            owner = contract.get("owner", "unknown")
            lines.append(f"- {node.get('id')} [{node_type}] → {target} | {status} | owner={owner}")
            lines.append(f"  生成内容：{generated}")
            lines.append(f"  边界：{note}")
            lines.append(f"  {self.node_action_hint(node)}")
        for flow in self.graph.get("flows", []):
            lines.append(f"- flow:{flow.get('id')} [{flow.get('type')}] → app_bootstrap.c / bind + scheduler")
        self.mapping_output.setPlainText("\n".join(lines))

    def refresh_structure_view(self) -> None:
        if not hasattr(self, "structure_output"):
            return
        modules = [node for node in self.graph.get("nodes", []) if node.get("type") == "project.module"]
        lines = ["项目结构解释", ""]
        if not modules:
            lines.append("- 未定义 project.module；所有节点暂时属于默认根模块。")
        for module in modules:
            mid = module.get("id")
            lines.append(f"▣ {mid} / {module.get('display_name', mid)}")
            for node in self.graph.get("nodes", []):
                if node.get("module") == mid:
                    lines.append(f"  - {node.get('id')} [{TYPE_LABELS.get(node.get('type'), node.get('type'))}]")
            lines.append("")
        loose = [node for node in self.graph.get("nodes", []) if node.get("type") != "project.module" and not node.get("module")]
        if loose:
            lines.append("未归属模块的节点：")
            for node in loose:
                lines.append(f"  - {node.get('id')} [{node.get('type')}]")
        self.structure_output.setPlainText("\n".join(lines))

    def refresh_file_tree_view(self) -> None:
        if not hasattr(self, "file_tree_output"):
            return
        custom_c = [item.get("path") for item in self.graph.get("custom_files", []) if str(item.get("path", "")).endswith(".c")]
        custom_h = [item.get("path") for item in self.graph.get("custom_files", []) if str(item.get("path", "")).endswith(".h")]
        lines = ["Graph → application/ 文件树预览", "application/generated_<project>/"]
        lines.extend(f"  {item}" for item in GENERATED_APPLICATION_TREE)
        for path in custom_h + custom_c:
            lines.append(f"  {path}                    # custom_files")
        self.file_tree_output.setPlainText("\n".join(lines))

    def refresh_schedule_view(self) -> None:
        if not hasattr(self, "schedule_output"):
            return
        tick = int(self.graph.get("project", {}).get("tick_ms", 1))
        lines = [f"任务调度视图（tick = {tick} ms）", ""]
        for flow in self.graph.get("flows", []):
            lines.append(f"- flow {flow.get('id')} [{flow.get('type')}] period={flow.get('period_ms', tick)}ms")
        for task in self.graph.get("tasks", []):
            target = task.get("call") or f"flow:{task.get('flow')}"
            lines.append(f"- task {task.get('id')} → {target} period={task.get('period_ms', tick)}ms")
        for node in self.graph.get("nodes", []):
            if node.get("type") == "task.periodic":
                target = node.get("call") or f"flow:{node.get('flow')}"
                lines.append(f"- node-task {node.get('id')} → {target} period={node.get('period_ms', tick)}ms")
        if len(lines) == 2:
            lines.append("暂无 flow/task。")
        self.schedule_output.setPlainText("\n".join(lines))

    def generation_readiness_lines(self) -> list[str]:
        missing_callbacks = self.missing_callback_requirements()
        doc_nodes = [node for node in self.graph.get("nodes", []) if not NODE_CONTRACTS.get(str(node.get("type")), {}).get("generated")]
        partial_nodes = [node for node in self.graph.get("nodes", []) if node_generation_label(str(node.get("type"))) == "部分生成"]
        hardware_mock_nodes = [node for node in self.graph.get("nodes", []) if node.get("type") in {"hal.gpio_line_input", "actuator.motor"}]
        custom_hardware_nodes = [node for node in self.graph.get("nodes", []) if node.get("type") in {"hal.custom", "sensor.custom", "actuator.custom"}]
        lines = ["生成就绪度："]
        lines.append(f"- 缺失用户回调：{len(missing_callbacks)} 个")
        lines.append(f"- 部分生成节点：{len(partial_nodes)} 个")
        lines.append(f"- 仅说明/组织节点：{len(doc_nodes)} 个")
        lines.append(f"- host mock 硬件节点：{len(hardware_mock_nodes)} 个")
        lines.append(f"- 需要真实 BSP/board_adapters 关注的自定义硬件节点：{len(custom_hardware_nodes)} 个")
        if missing_callbacks:
            lines.append("- 下一步：到 Code 页点击“一键生成缺失回调”，再补业务逻辑。")
        if any(node.get("type") == "event.publisher" for node in doc_nodes):
            lines.append("- 注意：event.publisher 不会自动 publish，请在 task/module/custom code 中调用 efw_topic_publish()。")
        if any(node.get("type") == "project.module" for node in doc_nodes):
            lines.append("- 注意：project.module 只做页面/分组，不生成独立模块文件。")
        if hardware_mock_nodes or custom_hardware_nodes:
            lines.append("- 注意：Board Profile/Pin Planner 只规划资源，真实板卡驱动仍在 board_adapters 中实现。")
        return lines

    def collect_pin_conflicts(self) -> list[str]:
        conflicts: list[str] = []
        seen_gpio: dict[tuple[str, int], str] = {}
        seen_pwm: dict[tuple[int, int], str] = {}
        for entry in self.graph.get("board", {}).get("pin_plan", []):
            owner = f"{entry.get('node')}:{entry.get('usage')}"
            if entry.get("port") not in (None, "") and entry.get("pin") not in (None, ""):
                key = (str(entry.get("port")).upper(), int(entry.get("pin")))
                if key in seen_gpio:
                    conflicts.append(f"GPIO {key[0]}{key[1]} 被 {seen_gpio[key]} 和 {owner} 重复使用")
                seen_gpio[key] = owner
            if entry.get("timer") not in (None, "") and entry.get("channel") not in (None, ""):
                key = (int(entry.get("timer")), int(entry.get("channel")))
                if key in seen_pwm:
                    conflicts.append(f"PWM TIM{key[0]} CH{key[1]} 被 {seen_pwm[key]} 和 {owner} 重复使用")
                seen_pwm[key] = owner
        return conflicts

    def add_graph_edge(self, src: dict[str, Any], dst: dict[str, Any], out_port: str = "out", in_port: str = "in", kind: str = "generic") -> None:
        edges = self.graph.setdefault("edges", [])
        src_id = src.get("id")
        dst_id = dst.get("id")
        if not src_id or not dst_id:
            return
        if self.active_page().get("kind") == "root" and src.get("type") == "project.module" and dst.get("type") == "project.module":
            out_port = out_port if out_port not in {"selected", "out"} else "module_output"
            in_port = in_port if in_port not in {"selected", "in"} else "module_input"
        kind = semantic_edge_kind(src, dst, out_port, in_port)
        for edge in edges:
            if edge.get("from") == src_id and edge.get("to") == dst_id and edge.get("from_port") == out_port and edge.get("to_port") == in_port:
                return
        self.push_undo()
        edges.append({"id": f"edge_{src_id}_{dst_id}_{len(edges) + 1}", "from": src_id, "to": dst_id, "from_port": out_port, "to_port": in_port, "kind": kind})

    def existing_custom_code(self) -> str:
        return "\n".join(item.get("content", "") for item in self.graph.get("custom_files", []))

    def callback_requirements(self) -> list[dict[str, str]]:
        requirements: list[dict[str, str]] = []
        for node in self.graph.get("nodes", []):
            contract = NODE_CONTRACTS.get(str(node.get("type")), {})
            for field, signature_key in contract.get("callbacks", {}).items():
                name = str(node.get(field, "")).strip()
                if name:
                    requirements.append({"owner": str(node.get("id")), "type": str(node.get("type")), "field": field, "name": name, "signature_key": signature_key})
        for task in self.graph.get("tasks", []):
            name = str(task.get("call", "")).strip()
            if name:
                requirements.append({"owner": str(task.get("id")), "type": "task.periodic", "field": "call", "name": name, "signature_key": "task.call"})
        return requirements

    def missing_callback_requirements(self) -> list[dict[str, str]]:
        existing_content = self.existing_custom_code()
        return [item for item in self.callback_requirements() if item["name"] not in existing_content]

    def callback_stub(self, requirement: dict[str, str]) -> str:
        name = requirement["name"]
        signature_key = requirement["signature_key"]
        params = CALLBACK_SIGNATURES.get(signature_key, "void")
        if signature_key == "topic.callback":
            return f"void {name}({params}) {{\n  EFW_UNUSED(topic_id);\n  EFW_UNUSED(data);\n  EFW_UNUSED(size);\n  EFW_UNUSED(user);\n}}\n"
        if signature_key == "condition":
            return f"int {name}(void) {{\n  /* TODO: return non-zero when this condition should pass. */\n  return 0;\n}}\n"
        body_lines = []
        if "ctx" in params:
            body_lines.append("  EFW_UNUSED(ctx);")
        if "buf" in params:
            body_lines.append("  EFW_UNUSED(buf);")
        if "len" in params:
            body_lines.append("  EFW_UNUSED(len);")
        if "actual" in params:
            if signature_key == "hal.write":
                body_lines.append("  if (actual) *actual = len;")
            else:
                body_lines.append("  if (actual) *actual = 0;")
        if "out" in params:
            body_lines.append("  EFW_UNUSED(out);")
        if "cmd" in params:
            body_lines.append("  EFW_UNUSED(cmd);")
        if "const void *in" in params or "void *in" in params:
            body_lines.append("  EFW_UNUSED(in);")
        if "uint32_t cmd" in params:
            body_lines.append("  EFW_UNUSED(cmd);")
        if "arg" in params:
            body_lines.append("  EFW_UNUSED(arg);")
        body_lines.append("  return EFW_OK;")
        return f"efw_status_t {name}({params}) {{\n" + "\n".join(body_lines) + "\n}\n"

    def callback_stubs(self) -> list[str]:
        seen: set[str] = set()
        stubs: list[str] = []
        for requirement in self.missing_callback_requirements():
            name = requirement["name"]
            if name in seen:
                continue
            seen.add(name)
            stubs.append(self.callback_stub(requirement))
        return stubs

    def refresh_callback_gap_view(self) -> None:
        if not hasattr(self, "callback_gap_output"):
            return
        missing = self.missing_callback_requirements()
        lines = ["缺失回调 / 用户代码行动项", ""]
        if missing:
            for item in missing:
                signature = callback_signature(item["signature_key"])
                lines.append(f"- {item['owner']}.{item['field']} -> {item['name']}: {signature}，建议生成到 app_custom.c 或放入 board_adapters。")
        else:
            lines.append("- 当前没有缺失回调。")
        doc_nodes = [node for node in self.graph.get("nodes", []) if not NODE_CONTRACTS.get(str(node.get("type")), {}).get("generated")]
        if doc_nodes:
            lines.append("")
            lines.append("仅说明/组织节点：")
            for node in doc_nodes:
                lines.append(f"- {node.get('id')} [{node.get('type')}]：{self.node_action_hint(node)}")
        self.callback_gap_output.setPlainText("\n".join(lines))

    def callback_stubs_legacy(self) -> list[str]:
        stubs: list[str] = []
        existing_content = "\n".join(item.get("content", "") for item in self.graph.get("custom_files", []))
        def has_symbol(name: str) -> bool:
            return bool(name) and name in existing_content
        for node in self.graph.get("nodes", []):
            ntype = node.get("type")
            for field, signature, body in [
                ("init", "efw_status_t {name}(void *ctx)", "    EFW_UNUSED(ctx);\n    return EFW_OK;"),
                ("read", "efw_status_t {name}(void *ctx, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
                ("write", "efw_status_t {name}(void *ctx, const void *cmd)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(cmd);\n    return EFW_OK;"),
                ("poll", "efw_status_t {name}(void *ctx)", "    EFW_UNUSED(ctx);\n    return EFW_OK;"),
                ("run", "efw_status_t {name}(void *ctx, const void *in, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(in);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
                ("process", "efw_status_t {name}(void *ctx, const void *in, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(in);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
            ]:
                name = node.get(field)
                if name and not has_symbol(str(name)):
                    if ntype == "hal.custom" and field == "read":
                        stubs.append(f"efw_status_t {name}(void *ctx, void *buf, uint16_t len, uint16_t *actual) {{\n    EFW_UNUSED(ctx);\n    EFW_UNUSED(buf);\n    EFW_UNUSED(len);\n    if (actual) *actual = 0;\n    return EFW_OK;\n}}\n")
                    elif ntype == "hal.custom" and field == "write":
                        stubs.append(f"efw_status_t {name}(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {{\n    EFW_UNUSED(ctx);\n    EFW_UNUSED(buf);\n    if (actual) *actual = len;\n    return EFW_OK;\n}}\n")
                    else:
                        stubs.append(signature.format(name=name) + " {\n" + body + "\n}\n")
            if ntype == "event.subscriber" and node.get("callback") and not has_symbol(str(node.get("callback"))):
                name = node.get("callback")
                stubs.append(f"void {name}(uint16_t topic_id, const void *data, uint16_t size, void *user) {{\n    EFW_UNUSED(topic_id);\n    EFW_UNUSED(data);\n    EFW_UNUSED(size);\n    EFW_UNUSED(user);\n}}\n")
            if ntype == "state.state":
                for field in ["on_enter", "on_update", "on_exit"]:
                    name = node.get(field)
                    if name and not has_symbol(str(name)):
                        stubs.append(f"efw_status_t {name}(void *ctx) {{\n    EFW_UNUSED(ctx);\n    return EFW_OK;\n}}\n")
            if ntype == "state.transition" and node.get("condition") and not has_symbol(str(node.get("condition"))):
                name = node.get("condition")
                stubs.append(f"int {name}(void) {{\n    return 0;\n}}\n")
            if ntype == "state.transition" and node.get("action") and not has_symbol(str(node.get("action"))):
                name = node.get("action")
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        for task in self.graph.get("tasks", []) + [n for n in self.graph.get("nodes", []) if n.get("type") == "task.periodic"]:
            name = task.get("call")
            if name and not has_symbol(str(name)):
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        return stubs


    def condition_stubs(self) -> list[str]:
        self.apply_code_file(record_history=False)
        existing_content = "\n".join(file.get("content", "") for file in self.graph.get("custom_files", []))
        stubs: list[str] = []
        for node in self.graph.get("nodes", []):
            if node.get("type") == "state.transition":
                name = str(node.get("condition", "")).strip()
                if name and name not in existing_content:
                    stubs.append(f"int {name}(void) {{\n  /* TODO: return non-zero when this condition should pass. */\n  return 0;\n}}\n")
        return stubs

    def generate_condition_callbacks(self) -> None:
        stubs = self.condition_stubs()
        if not stubs:
            QMessageBox.information(self, "条件函数", "没有发现需要生成的条件函数。")
            return
        files = self.graph.setdefault("custom_files", [])
        if not files:
            files.append({"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"})
        files[0]["content"] = files[0].get("content", "") + "\n/* Auto-generated condition stubs */\n" + "\n".join(stubs)
        self.current_code_index = 0
        self.refresh_code_list()
        self.select_code_file(0)
        self.refresh_json_editor()
        QMessageBox.information(self, "条件函数", f"已生成 {len(stubs)} 个条件函数 stub。")

    def generate_missing_callbacks(self) -> None:
        self.apply_code_file(record_history=False)
        stubs = self.callback_stubs()
        if not stubs:
            QMessageBox.information(self, "缺失回调", "没有发现需要生成的缺失回调。")
            return
        files = self.graph.setdefault("custom_files", [])
        if not files:
            files.append({"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"})
        files[0]["content"] = files[0].get("content", "") + "\n/* Auto-generated missing callback stubs */\n" + "\n".join(stubs)
        self.current_code_index = 0
        self.refresh_code_list()
        self.refresh_json_editor()
        QMessageBox.information(self, "缺失回调", f"已生成 {len(stubs)} 个回调 stub 到 {files[0].get('path')}。")

    def _validation_target_from_message(self, message: str) -> str | None:
        ids = {str(node.get("id")) for node in self.graph.get("nodes", [])}
        for node_id in sorted(ids, key=len, reverse=True):
            if node_id and node_id in message:
                return node_id
        return None

    def open_validation_item(self, item: QListWidgetItem) -> None:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        node_id = item.data(role)
        if not node_id:
            return
        self.open_node_location(str(node_id))

    def refresh_validation_panel(self, show_dialog: bool = False) -> bool:
        messages: list[str] = []
        ok = True
        try:
            self.apply_code_file(record_history=False)
            validate_graph(self.graph)
            edge_count = len(self.graph.get("edges", []))
            by_generation: dict[str, list[str]] = {}
            for node in self.graph.get("nodes", []):
                label = node_generation_label(str(node.get("type"))) if node.get("type") in NODE_CONTRACTS else "未知"
                by_generation.setdefault(label, []).append(str(node.get("id")))
            messages.append(f"✅ Graph 校验通过：ID、引用、周期、回调函数和签名均有效。统一 edges: {edge_count} 条")
            for label, ids in by_generation.items():
                messages.append(f"ℹ️ {label} 节点：" + ", ".join(ids))
            messages.extend(self.generation_readiness_lines())
        except Exception as exc:  # noqa: BLE001 - UI validation panel shows validator message.
            messages.append(f"❌ Graph 校验失败：{exc}")
            ok = False
        conflicts = self.collect_pin_conflicts()
        for conflict in conflicts:
            messages.append(f"⚠️ Pin Planner 冲突：{conflict}")
        ok = ok and not conflicts
        for node in self.graph.get("nodes", []):
            if node.get("type") == "state.transition" and not str(node.get("condition", "")).strip():
                messages.append(f"❌ {node.get('id')}.condition 为空：transition 必须填写条件函数")
                ok = False
        text = "\n".join(messages)
        self.validation_messages = messages
        self.validation_targets = [self._validation_target_from_message(message) for message in messages]
        if hasattr(self, "validation_output"):
            self.validation_output.setPlainText(text)
        if hasattr(self, "validation_list"):
            role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
            self.validation_list.clear()
            grouped: dict[str, list[str]] = {}
            ungrouped: list[tuple[str, str | None]] = []
            for message, target in zip(messages, self.validation_targets):
                if target and (message.startswith("❌") or message.startswith("⚠️")):
                    grouped.setdefault(target, []).append(message)
                else:
                    ungrouped.append((message, target))
            for target, target_messages in grouped.items():
                header = QListWidgetItem(f"节点 {target}：{len(target_messages)} 个问题")
                header.setData(role, target)
                header.setToolTip(f"点击定位到卡片：{target}")
                header.setBackground(QBrush(QColor("#263746")))
                header.setForeground(QBrush(QColor("#ffffff")))
                self.validation_list.addItem(header)
                for message in target_messages:
                    child = QListWidgetItem("  " + message)
                    child.setData(role, target)
                    child.setToolTip(f"点击定位到卡片：{target}")
                    if message.startswith("❌"):
                        child.setBackground(QBrush(QColor("#5b1f24")))
                        child.setForeground(QBrush(QColor("#ffb3b3")))
                    elif message.startswith("⚠️"):
                        child.setBackground(QBrush(QColor("#4f3b13")))
                        child.setForeground(QBrush(QColor("#ffe0a3")))
                    self.validation_list.addItem(child)
            for message, target in ungrouped:
                item = QListWidgetItem(message)
                if target:
                    item.setData(role, target)
                    item.setToolTip(f"点击定位到卡片：{target}")
                self.validation_list.addItem(item)
        if show_dialog:
            if ok:
                QMessageBox.information(self, "校验通过", text)
            else:
                QMessageBox.warning(self, "校验失败", text)
        return ok

    def begin_port_drag(self, port: PortItem) -> None:
        self.drag_port = port
        center = port.sceneBoundingRect().center()
        self.drag_line = QGraphicsLineItem(center.x(), center.y(), center.x(), center.y())
        self.drag_line.setPen(QPen(QColor("#29b6f6"), 2))
        self.drag_line.setZValue(10)
        self.scene.addItem(self.drag_line)

    def update_port_drag(self, pos: QPointF) -> None:
        if not self.drag_line or not self.drag_port:
            return
        start = self.drag_port.sceneBoundingRect().center()
        self.drag_line.setLine(start.x(), start.y(), pos.x(), pos.y())

    def finish_port_drag(self, pos: QPointF, released_port: PortItem) -> None:
        start_port = self.drag_port
        if self.drag_line:
            self.scene.removeItem(self.drag_line)
        self.drag_line = None
        self.drag_port = None
        target = self.port_at(pos)
        if not start_port or not target or target is start_port:
            return
        if start_port.direction == target.direction:
            self.flash_invalid_connection(target)
            QMessageBox.warning(self, "连接无效", "必须从输出端口拖到输入端口，不能连接同方向端口。")
            return
        out_port = start_port if start_port.direction == "out" else target
        in_port = target if target.direction == "in" else start_port
        if not self.connect_ports(out_port, in_port):
            self.flash_invalid_connection(in_port)
            QMessageBox.warning(self, "连接无效", self.connection_failure_reason(out_port, in_port))
        self.refresh_all()

    def port_at(self, pos: QPointF) -> PortItem | None:
        for item in self.scene.items(pos):
            if isinstance(item, PortItem):
                return item
        return None

    def flash_invalid_connection(self, port: PortItem) -> None:
        port.setBrush(QBrush(QColor("#e53935")))

    def connect_ports(self, out_port: PortItem, in_port: PortItem) -> bool:
        src = out_port.node_item.node
        dst = in_port.node_item.node
        if not can_connect_ports(src, dst, out_port.port_type, in_port.port_type):
            return False
        if not self._connect_pair(src, dst):
            return False
        self.add_graph_edge(src, dst, out_port.port_type, in_port.port_type, "port")
        return True

    def connection_failure_reason(self, out_port: PortItem, in_port: PortItem) -> str:
        src = out_port.node_item.node
        dst = in_port.node_item.node
        from_label = PORT_LABELS.get(out_port.port_type, out_port.port_type)
        to_label = PORT_LABELS.get(in_port.port_type, in_port.port_type)
        src_label = f"{src.get('id')} ({TYPE_LABELS.get(src.get('type'), src.get('type'))})"
        dst_label = f"{dst.get('id')} ({TYPE_LABELS.get(dst.get('type'), dst.get('type'))})"
        if src.get("id") == dst.get("id"):
            return "不能把卡片连接到自身；请连接到另一个节点。"
        effect = edge_effect_description(src, dst, out_port.port_type, in_port.port_type)
        if not pair_has_semantics(src, dst):
            return f"{src_label} -> {dst_label} 没有定义 Graph 语义；当前不会自动推导字段或生成代码关系。"
        return f"端口类型不兼容：{from_label}({out_port.port_type}) 不能连接到 {to_label}({in_port.port_type})。\n输出端口说明：{PORT_DESCRIPTIONS.get(out_port.port_type, '无')}\n输入端口说明：{PORT_DESCRIPTIONS.get(in_port.port_type, '无')}\n如果改用兼容端口，本关系的生成/语义效果：{effect}"


    def connect_selected_cards(self) -> None:
        QMessageBox.information(self, "端口连线", "请从卡片右侧输出端口圆点拖拽到另一张卡片左侧输入端口圆点；Studio 不再支持中心点选中连线。")

    def _connect_pair(self, src: dict[str, Any], dst: dict[str, Any]) -> bool:
        self.push_undo()
        connected = apply_pair_semantics(src, dst, self.graph, c_ident_func=c_ident, overwrite=True)
        if connected and src.get("type") == "custom.code":
            QMessageBox.information(self, "Connect cards", "Use the Code tab to implement callbacks named by the selected custom card.")
        return connected

    def apply_node_json(self) -> None:
        if not self.current_node_id:
            return
        try:
            self.push_undo()
            updated = json.loads(self.node_json_editor.toPlainText())
            if not isinstance(updated, dict):
                raise ValueError("card JSON must be an object")
            old_id = str(self.current_node_id)
            new_id = str(updated.get("id", old_id))
            if new_id != old_id:
                self.rename_node_references(old_id, new_id)
            nodes = self.graph.get("nodes", [])
            for idx, node in enumerate(nodes):
                if node.get("id") == old_id or node.get("id") == new_id:
                    nodes[idx] = updated
                    self.current_node_id = new_id
                    break
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "卡片 JSON 无效", str(exc))

    def delete_selected_node(self) -> None:
        if not self.current_node_id:
            return
        self.push_undo()
        self.graph["nodes"] = [node for node in self.graph.get("nodes", []) if node.get("id") != self.current_node_id]
        ui = self.graph.get("ui", {})
        ui.get("positions", {}).pop(self.current_node_id, None)
        for page_positions in ui.get("positions_by_page", {}).values():
            page_positions.pop(self.current_node_id, None)
        self.current_node_id = None
        self.refresh_all()

    def select_code_file(self, row: int) -> None:
        self.current_code_index = row if row >= 0 else None
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index is None or self.current_code_index >= len(files):
            self.code_editor.clear()
            if hasattr(self, "code_status_label"):
                self.code_status_label.setText("未选择文件")
            return
        item = files[self.current_code_index]
        content = item.get("content", "")
        self.code_editor.setPlainText(content)
        if hasattr(self, "code_status_label"):
            self.code_status_label.setText(f"{item.get('path', 'unnamed')} · {content.count(chr(10)) + 1} 行")

    def add_code_file(self) -> None:
        path, ok = QInputDialog.getText(self, "Add custom code", "Relative file path (for example app_custom.c):")
        if not ok or not path:
            return
        self.push_undo()
        self.graph.setdefault("custom_files", []).append({"path": path, "content": DEFAULT_CUSTOM_C if path.endswith(".c") else ""})
        self.current_code_index = len(self.graph["custom_files"]) - 1
        self.refresh_code_list()
        self.refresh_json_editor()

    def apply_code_file(self, record_history: bool = True) -> None:
        if self.current_code_index is None:
            return
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index >= len(files):
            return
        if record_history:
            self.push_undo()
        files[self.current_code_index]["content"] = self.code_editor.toPlainText()
        if hasattr(self, "code_status_label"):
            self.code_status_label.setText(f"{files[self.current_code_index].get('path', 'unnamed')} · 已保存")
        self.refresh_json_editor()

    def format_code_file(self) -> None:
        text = self.code_editor.toPlainText()
        self.code_editor.setPlainText(self.format_c_like_code(text))

    def format_c_like_code(self, text: str) -> str:
        protected: list[str] = []

        def protect_comment(match):
            protected.append(match.group(0))
            return f"__COMMENT_{len(protected) - 1}__"

        import re
        text = text.replace("\r\n", "\n").replace("\t", "  ")
        text = re.sub(r"/\*.*?\*/", protect_comment, text, flags=re.S)
        text = re.sub(r"\s*([{};])\s*", r"\1\n", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        raw_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                raw_lines.append("")
                continue
            if stripped.startswith("#"):
                raw_lines.append(stripped)
                continue
            if stripped in {"{", "}", ";"}:
                raw_lines.append(stripped)
                continue
            raw_lines.append(stripped)

        result = []
        indent = 0
        previous_blank = False
        for line in raw_lines:
            if not line:
                if not previous_blank:
                    result.append("")
                previous_blank = True
                continue
            previous_blank = False
            if line.startswith("}"):
                indent = max(0, indent - 1)
            if line == ";":
                if result:
                    result[-1] = result[-1].rstrip() + ";"
                continue
            if line == "{":
                if result and not result[-1].strip().startswith("#"):
                    result[-1] = result[-1].rstrip() + " {"
                else:
                    result.append("  " * indent + "{")
                indent += 1
                continue
            result.append("  " * indent + line)
            if line.endswith("{"):
                indent += 1
        formatted = "\n".join(result).strip()
        for index, comment in enumerate(protected):
            formatted = formatted.replace(f"__COMMENT_{index}__", comment)
        return formatted + "\n"

    def delete_code_file(self) -> None:
        if self.current_code_index is None:
            return
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index < len(files):
            self.push_undo()
            del files[self.current_code_index]
        self.current_code_index = None
        self.refresh_code_list()
        self.refresh_json_editor()

    def apply_full_json(self) -> None:
        try:
            graph = json.loads(self.graph_json_editor.toPlainText())
            if not isinstance(graph, dict):
                raise ValueError("graph JSON must be an object")
            self.push_undo()
            self.graph = graph
            self.current_node_id = None
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "Graph JSON 无效", str(exc))

    def validate_current_graph(self) -> bool:
        return self.refresh_validation_panel(show_dialog=True)

    def project_wizard(self) -> None:
        templates = {
            "通用嵌入式应用": self.default_graph,
            "空白多模块项目": lambda: {"project": {"name": "new_modular_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}], "ui": {"positions": {"control_module": [40, 40]}}},
            "状态机项目": lambda: {"project": {"name": "state_machine_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"]), copy.deepcopy(NODE_TEMPLATES["state.machine"]), copy.deepcopy(NODE_TEMPLATES["state.state"]), copy.deepcopy(NODE_TEMPLATES["state.transition"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}], "ui": {"positions": {}}},
        }
        choice, ok = QInputDialog.getItem(self, "项目向导", "选择模板", list(templates), 0, False)
        if not ok or not choice:
            return
        self.graph_path = None
        self.push_undo()
        self.graph = templates[choice]()
        self.current_node_id = None
        self.refresh_all()

    def new_graph(self) -> None:
        self.push_undo()
        self.graph_path = None
        self.graph = self.default_graph()
        self.current_node_id = None
        self.refresh_all()

    def open_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 Graph", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.push_undo()
        self.graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.current_node_id = None
        self.refresh_all()

    def save_graph(self) -> None:
        if not self.graph_path:
            self.save_graph_as()
            return
        self.apply_code_file(record_history=False)
        self.graph_path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.refresh_json_editor()

    def save_graph_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存 Graph", str(REPO_ROOT / "examples" / "graphs" / "line_tracking_car.json"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.save_graph()

    def generate_application(self) -> None:
        self.apply_code_file(record_history=False)
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出 application 目录")
        if not out_dir:
            return
        out_path = Path(out_dir)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(self.graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            preview = preview_application_files(tmp_path, out_path)
            def preview_line(item: dict[str, Any]) -> str:
                sha = f" {item.get('old_sha', 'new')}→{item.get('new_sha', '')}" if item.get("new_sha") else ""
                lines = f" lines:{item.get('old_lines', '-')}→{item.get('new_lines', '-')}" if item.get("new_lines") else ""
                protection = f" ({item.get('protected_by')})" if item.get("protected_by") else ""
                return f"{item['status']}: {item['path']}{sha}{lines}{protection}"
            summary = "\n".join(preview_line(item) for item in preview[:60])
            force = False
            if out_path.exists() and any(out_path.iterdir()):
                answer = QMessageBox.question(self, "Diff 预览 / 覆盖确认", f"输出目录已存在且非空，非生成文件会保留：\n{out_path}\n\n{summary}\n\n是否覆盖生成文件？")
                yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
                if answer != yes:
                    tmp_path.unlink(missing_ok=True)
                    return
                force = True
            generate(tmp_path, out_path, force=force)
            tmp_path.unlink(missing_ok=True)
            created = sum(1 for item in preview if item.get("status") == "create")
            overwritten = sum(1 for item in preview if item.get("status") == "backup+overwrite")
            preserved = sum(1 for item in preview if item.get("status") == "preserve")
            next_steps = "\n".join(self.generation_readiness_lines())
            QMessageBox.information(self, "已生成", f"已生成 EFW application:\n{out_path}\n\n文件摘要：create={created}, overwrite={overwritten}, preserve={preserved}\n\n{next_steps}\n\n下一步：用 CMake/Keil 验证生成工程；真实板卡请补 board_adapters。")
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "生成失败", str(exc))


def main() -> int:
    print("studio.editor 现在只作为内嵌蓝图编辑器模块；请使用统一入口：python3 tools/efw.py studio", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
