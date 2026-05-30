#!/usr/bin/env python3
"""PyQt visual graph + code editor for the EFW application generator.

This is the second milestone of the blueprint workflow: users can create known
EFW cards visually, edit their JSON properties, write custom C/H files in the
same project, and invoke tools/efw_codegen.py to export an application folder.
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
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QFont, QPen
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
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import QPointF, Qt
    from PyQt5.QtGui import QBrush, QColor, QFont, QPen
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
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QApplication = None
    QFileDialog = QInputDialog = QMessageBox = None
    QBrush = QColor = QFont = QPen = QPointF = Qt = object
    QComboBox = QFormLayout = QGraphicsEllipseItem = QGraphicsItem = object
    QGraphicsLineItem = QGraphicsRectItem = QGraphicsScene = QGraphicsSimpleTextItem = QGraphicsView = object
    QHBoxLayout = QLabel = QListWidget = QListWidgetItem = QMainWindow = object
    QLineEdit = QPushButton = QPlainTextEdit = QSplitter = QTableWidget = QTableWidgetItem = object
    QTabWidget = QToolBar = QVBoxLayout = QWidget = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from efw_codegen import c_ident, generate, preview_application_files, validate_graph  # noqa: E402
from efw_visual_model import BOARD_PROFILES, GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS, VISUAL_NODE_CATEGORIES  # noqa: E402



def discover_framework_templates() -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Scan EFW public headers and expose graph templates for the palette.

    The scan is intentionally conservative: it only creates templates that can
    be represented by the current generator schema, and it records the source
    header so users can see which framework API the card came from.
    """
    templates: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    include_root = REPO_ROOT / "include" / "efw"
    if not include_root.exists():
        return templates, order

    def add_template(key: str, template: dict[str, Any], header: Path) -> None:
        if key in templates:
            return
        template["framework_header"] = header.relative_to(REPO_ROOT).as_posix()
        template.setdefault("note", f"从框架头文件 {template['framework_header']} 自动扫描得到；生成时仍会按当前 schema 校验回调。")
        templates[key] = template
        order.append(key)

    skip_stems = {"algorithms", "registry", "sensor", "actuator"}
    for header in sorted(include_root.rglob("*.h")):
        rel = header.relative_to(include_root)
        stem = header.stem
        if stem in skip_stems:
            continue
        parts = rel.parts
        if parts[:2] == ("device", "sensor") and stem not in {"line_tracking", "custom"}:
            template = copy.deepcopy(NODE_TEMPLATES["sensor.custom"])
            template.update({"id": f"sensor_{stem}", "sensor_type": stem, "read": f"app_sensor_{stem}_read"})
            add_template(f"scan.sensor.{stem}", template, header)
        elif parts[:2] == ("device", "actuator") and stem not in {"motor"}:
            template = copy.deepcopy(NODE_TEMPLATES["actuator.custom"])
            template.update({"id": f"actuator_{stem}", "actuator_type": stem, "write": f"app_actuator_{stem}_write"})
            add_template(f"scan.actuator.{stem}", template, header)
        elif parts[0] == "algorithm":
            template = copy.deepcopy(NODE_TEMPLATES["algorithm.custom"])
            template.update({"id": f"algo_{stem}", "run": f"app_algo_{stem}_run", "algo_type": "EFW_ALGO_CUSTOM"})
            add_template(f"scan.algorithm.{stem}", template, header)
        elif parts == ("hal", "hal.h"):
            for hal_type in ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer"]:
                template = copy.deepcopy(NODE_TEMPLATES["hal.custom"])
                template.update({"id": f"hal_{hal_type}", "hal_type": hal_type, "init": f"app_hal_{hal_type}_init"})
                add_template(f"scan.hal.{hal_type}", template, header)
        elif parts == ("module", "module.h"):
            template = copy.deepcopy(NODE_TEMPLATES["module.custom"])
            template.update({"id": "module_service", "module_type": "EFW_MODULE_SERVICE"})
            add_template("scan.module.service", template, header)
        elif parts == ("core", "event.h"):
            template = copy.deepcopy(NODE_TEMPLATES["event.topic"])
            template.update({"id": "topic_event", "payload_type": "custom"})
            add_template("scan.event.topic", template, header)
        elif parts == ("state", "state_machine.h"):
            template = copy.deepcopy(NODE_TEMPLATES["state.machine"])
            template.update({"id": "scanned_state_machine"})
            add_template("scan.state.machine", template, header)
    return templates, order

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
        "ctx": "0",
        "run": "app_custom_algo_run",
        "io_contract": "custom",
    },
    "module.custom": {
        "id": "custom_module",
        "type": "module.custom",
        "module_type": "EFW_MODULE_CUSTOM",
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
    },
    "logic.if": {
        "id": "if_condition",
        "type": "logic.if",
        "condition": "app_condition",
        "then": "",
        "else": "",
    },
    "logic.loop": {
        "id": "loop_block",
        "type": "logic.loop",
        "loop": "while",
        "condition": "app_loop_condition",
        "body": "",
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

FRAMEWORK_SCAN_TEMPLATES, FRAMEWORK_SCAN_ORDER = discover_framework_templates()
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

PORT_RULES = {
    "hal.gpio_line_input": {"out": ["hal"]},
    "hal.custom": {"out": ["hal"]},
    "sensor.line_tracking": {"in": ["hal"], "out": ["sensor"]},
    "sensor.custom": {"in": ["hal"], "out": ["sensor"]},
    "algorithm.pid": {"in": ["sensor"], "out": ["algorithm"]},
    "algorithm.custom": {"in": ["sensor"], "out": ["algorithm"]},
    "actuator.motor": {"in": ["control"]},
    "actuator.custom": {"in": ["hal", "control"]},
    "module.custom": {"in": ["sensor", "algorithm", "event"], "out": ["module"]},
    "task.periodic": {"in": ["module", "flow"]},
    "project.module": {"out": ["group"]},
    "event.topic": {"out": ["topic"]},
    "event.publisher": {"in": ["module", "sensor", "topic"], "out": ["event"]},
    "event.subscriber": {"in": ["topic"], "out": ["event"]},
    "state.machine": {"out": ["state"]},
    "state.state": {"in": ["state"], "out": ["state"]},
    "state.transition": {"in": ["state"], "out": ["state"]},
    "logic.if": {"in": ["event", "sensor"], "out": ["logic"]},
    "logic.loop": {"in": ["logic"], "out": ["logic"]},
}

PORT_COLORS = {
    "hal": "#26c6da",
    "sensor": "#66bb6a",
    "algorithm": "#ab47bc",
    "control": "#ec407a",
    "module": "#ffb300",
    "flow": "#42a5f5",
    "group": "#7e57c2",
    "topic": "#ef5350",
    "event": "#ff7043",
    "state": "#26a69a",
    "logic": "#d4e157",
}

NODE_THEMES = {
    "hal": {"bg": "#12313a", "border": "#26c6da", "accent": "#00acc1"},
    "sensor": {"bg": "#17361f", "border": "#66bb6a", "accent": "#43a047"},
    "actuator": {"bg": "#3a2512", "border": "#ffa726", "accent": "#fb8c00"},
    "algorithm": {"bg": "#301a3a", "border": "#ab47bc", "accent": "#8e24aa"},
    "module": {"bg": "#3a3012", "border": "#ffca28", "accent": "#f9a825"},
    "task": {"bg": "#1b2d48", "border": "#42a5f5", "accent": "#1e88e5"},
    "project": {"bg": "#241b48", "border": "#7e57c2", "accent": "#5e35b1"},
    "event": {"bg": "#481f1b", "border": "#ef5350", "accent": "#e53935"},
    "state": {"bg": "#123a35", "border": "#26a69a", "accent": "#00897b"},
    "logic": {"bg": "#343812", "border": "#d4e157", "accent": "#afb42b"},
    "custom": {"bg": "#30343b", "border": "#90a4ae", "accent": "#607d8b"},
}

WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { background: #101820; color: #e8f0f2; font-family: "Noto Sans CJK SC", "Microsoft YaHei", "WenQuanYi Micro Hei", "DejaVu Sans"; }
QToolBar { background: #162532; border-bottom: 1px solid #29465c; spacing: 6px; }
QToolButton, QPushButton {
    background: #1f3a4d;
    color: #f5fbff;
    border: 1px solid #3f6b82;
    border-radius: 5px;
    padding: 5px 9px;
}
QToolButton:hover, QPushButton:hover { background: #28516a; border-color: #5fa8c8; }
QTabWidget::pane { border: 1px solid #29465c; }
QTabBar::tab { background: #172733; color: #c9d8df; padding: 7px 10px; border: 1px solid #29465c; }
QTabBar::tab:selected { background: #24475d; color: #ffffff; }
QListWidget, QTableWidget, QPlainTextEdit, QLineEdit {
    background: #0d141b;
    color: #e8f0f2;
    border: 1px solid #29465c;
    selection-background-color: #2d6f8f;
}
QHeaderView::section { background: #1b3444; color: #e8f0f2; border: 1px solid #29465c; padding: 4px; }
QLabel { color: #e8f0f2; }
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
    "module.custom": "模块 · 自定义",
    "task.periodic": "任务 · 周期",
    "project.module": "项目 · 模块分组",
    "event.topic": "通信 · Topic",
    "event.publisher": "通信 · 发布者",
    "event.subscriber": "通信 · 订阅者",
    "state.machine": "状态机 · 容器",
    "state.state": "状态机 · 状态",
    "state.transition": "状态机 · 转换",
    "logic.if": "逻辑 · if条件",
    "logic.loop": "逻辑 · 循环",
    "custom.card": "说明卡片",
    "custom.code": "代码卡片",
}

NODE_CATEGORIES = [(name, FRAMEWORK_SCAN_ORDER if name == "框架库扫描" else types) for name, types in VISUAL_NODE_CATEGORIES]


def display_label(template_key: str) -> str:
    template = NODE_TEMPLATES.get(template_key, {})
    node_type = template.get("type", template_key)
    if template_key.startswith("scan."):
        return f"框架扫描 · {template.get('id', template_key)}"
    return TYPE_LABELS.get(node_type, TYPE_LABELS.get(template_key, template_key))


def node_summary(node: dict[str, Any]) -> str:
    node_type = node.get("type", "")
    if node_type == "actuator.motor":
        pwm = node.get("pwm", {})
        direction = node.get("dir_pin", {})
        return f"PWM=T{pwm.get('timer')}/CH{pwm.get('channel')} · DIR={direction.get('port')}{direction.get('pin')}"
    if node_type == "hal.gpio_line_input":
        pins = node.get("pins", [])
        first = pins[0] if pins else {}
        return f"channels={node.get('channels')} · first={first.get('port')}{first.get('pin')}"
    keys_by_type = {
        "algorithm.pid": ["kp", "ki", "kd", "out_min", "out_max"],
        "task.periodic": ["period_ms", "call"],
        "state.transition": ["from", "to", "condition"],
        "logic.if": ["condition", "then", "else"],
        "logic.loop": ["condition", "body", "max_iterations"],
        "event.topic": ["topic_id", "payload_type"],
        "event.subscriber": ["topic", "callback"],
        "project.module": ["display_name"],
        "hal.custom": ["hal_type", "bus_id"],
        "sensor.custom": ["sensor_type", "hal_name", "read"],
        "actuator.custom": ["actuator_type", "hal_name", "write"],
    }
    keys = keys_by_type.get(node_type, ["module", "period_ms"])
    parts = [f"{key}={node.get(key)}" for key in keys if node.get(key) not in (None, "", [])]
    return " · ".join(parts[:3])


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


class PortItem(QGraphicsEllipseItem):
    SIZE = 12

    def __init__(self, node_item: "GraphNodeItem", direction: str, port_type: str, index: int):
        super().__init__(0, 0, self.SIZE, self.SIZE, node_item)
        self.node_item = node_item
        self.direction = direction
        self.port_type = port_type
        base = QColor(PORT_COLORS.get(port_type, "#90a4ae"))
        self.setBrush(QBrush(base.lighter(115) if direction == "out" else base.darker(115)))
        self.setPen(QPen(QColor("#ffffff"), 1))
        y = 18 + index * 18
        x = node_item.WIDTH - self.SIZE / 2 if direction == "out" else -self.SIZE / 2
        self.setPos(x, y)
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
        self.setPen(QPen(QColor(theme["border"]), 2))
        accent = QGraphicsRectItem(0, 0, self.WIDTH, 7, self)
        accent.setBrush(QBrush(QColor(theme["accent"])))
        accent.setPen(QPen(QColor(theme["accent"]), 0))
        title = QGraphicsSimpleTextItem(node.get("id", "node"), self)
        title.setBrush(QBrush(QColor("#ffffff")))
        bold_weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
        title.setFont(QFont("Sans", 10, bold_weight))
        title.setPos(8, 8)
        label = TYPE_LABELS.get(node.get("type"), node.get("type", "unknown"))
        subtitle = QGraphicsSimpleTextItem(label, self)
        subtitle.setBrush(QBrush(QColor("#d7e6ec")))
        subtitle.setPos(8, 29)
        summary_text = node_summary(node)
        if summary_text:
            summary = QGraphicsSimpleTextItem(summary_text[:34], self)
            summary.setBrush(QBrush(QColor("#b8cad1")))
            summary.setPos(8, 49)
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
        if self.node.get("type") == "project.module":
            self.editor.enter_module(self.node.get("id"))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class VisualEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"EFW 嵌入式蓝图工作台 ({QT_LIB})")
        self.resize(1280, 760)
        self.graph_path: Path | None = None
        self.current_node_id: str | None = None
        self.current_code_index: int | None = None
        self.node_items: dict[str, GraphNodeItem] = {}
        self.edge_items: list[QGraphicsLineItem] = []
        self.drag_line: QGraphicsLineItem | None = None
        self.drag_port: PortItem | None = None
        self.validation_messages: list[str] = []
        self.active_module_id: str | None = None
        self.graph = self.default_graph()
        self.setStyleSheet(WORKBENCH_STYLESHEET)
        self._build_ui()
        self.refresh_all()

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
                {"id": "edge_system_uart", "from": "system_core", "to": "uart_debug", "from_port": "group", "to_port": "node", "kind": "module_contains"},
                {"id": "edge_topic_subscriber", "from": "topic_battery", "to": "subscribe_battery", "from_port": "topic", "to_port": "topic", "kind": "event_subscribe"},
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
        toolbar = QToolBar("主工具栏")
        self.addToolBar(toolbar)
        toolbar.addAction("新建", self.new_graph)
        toolbar.addAction("项目向导", self.project_wizard)
        toolbar.addAction("打开", self.open_graph)
        toolbar.addAction("保存", self.save_graph)
        toolbar.addAction("另存为", self.save_graph_as)
        toolbar.addAction("实时校验", self.validate_current_graph)
        toolbar.addAction("生成", self.generate_application)
        toolbar.addAction("连接选中", self.connect_selected_cards)
        toolbar.addAction("自动布局", self.auto_layout)
        toolbar.addAction("返回根模块", self.exit_module)

        root_splitter = QSplitter()
        self.setCentralWidget(root_splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("模板库 / 组件市场"))
        self.palette = QListWidget()
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
        add_btn = QPushButton("添加卡片")
        add_btn.clicked.connect(self.add_selected_card)
        left_layout.addWidget(add_btn)
        root_splitter.addWidget(left)

        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        self.module_scope_label = QLabel("当前视图：根项目")
        canvas_layout.addWidget(self.module_scope_label)
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        canvas_layout.addWidget(self.view)
        root_splitter.addWidget(canvas)

        right_tabs = QTabWidget()
        right_tabs.addTab(self._build_properties_tab(), "属性表单")
        right_tabs.addTab(self._build_pin_planner_tab(), "Board Profile / Pin Planner")
        right_tabs.addTab(self._build_validation_tab(), "实时校验")
        right_tabs.addTab(self._build_mapping_tab(), "生成映射")
        right_tabs.addTab(self._build_structure_tab(), "项目结构")
        right_tabs.addTab(self._build_file_tree_tab(), "文件树预览")
        right_tabs.addTab(self._build_schedule_tab(), "任务调度")
        right_tabs.addTab(self._build_code_tab(), "代码")
        right_tabs.addTab(self._build_json_tab(), "Graph JSON")
        root_splitter.addWidget(right_tabs)
        root_splitter.setSizes([210, 650, 420])

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.selected_label = QLabel("未选择卡片")
        layout.addWidget(self.selected_label)
        self.property_table = QTableWidget(0, 3)
        self.property_table.setHorizontalHeaderLabels(["属性", "值", "控件类型"])
        layout.addWidget(self.property_table)
        apply_form_btn = QPushButton("应用表单")
        apply_form_btn.clicked.connect(self.apply_property_form)
        layout.addWidget(apply_form_btn)
        layout.addWidget(QLabel("高级 JSON（复杂数组/对象可在这里编辑）"))
        self.node_json_editor = QPlainTextEdit()
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
        layout.addWidget(QLabel("Board Profile 与 Pin Planner：修改 GPIO/PWM 后点击应用，会写回 Graph 节点。"))
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

    def _build_code_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        row = QHBoxLayout()
        self.code_files = QListWidget()
        self.code_files.currentRowChanged.connect(self.select_code_file)
        row.addWidget(self.code_files, 1)
        self.code_editor = QPlainTextEdit()
        row.addWidget(self.code_editor, 3)
        layout.addLayout(row)
        controls = QHBoxLayout()
        add_btn = QPushButton("Add .c/.h")
        add_btn.clicked.connect(self.add_code_file)
        apply_btn = QPushButton("Apply Code")
        apply_btn.clicked.connect(self.apply_code_file)
        delete_btn = QPushButton("Delete Code")
        delete_btn.clicked.connect(self.delete_code_file)
        stub_btn = QPushButton("一键生成缺失回调")
        stub_btn.clicked.connect(self.generate_missing_callbacks)
        controls.addWidget(add_btn)
        controls.addWidget(apply_btn)
        controls.addWidget(delete_btn)
        controls.addWidget(stub_btn)
        layout.addLayout(controls)
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
        self.refresh_scene()
        self.refresh_json_editor()
        self.refresh_code_list()
        self.refresh_pin_planner()
        self.refresh_mapping_view()
        self.refresh_structure_view()
        self.refresh_file_tree_view()
        self.refresh_schedule_view()
        self.refresh_validation_panel(show_dialog=False)
        self.select_node(self.current_node_id)

    def visible_nodes(self) -> list[dict[str, Any]]:
        if not self.active_module_id:
            return self.graph.get("nodes", [])
        return [node for node in self.graph.get("nodes", []) if node.get("id") == self.active_module_id or node.get("module") == self.active_module_id]

    def enter_module(self, module_id: str | None) -> None:
        if not module_id:
            return
        self.active_module_id = module_id
        self.refresh_all()

    def exit_module(self) -> None:
        self.active_module_id = None
        self.refresh_all()

    def refresh_scene(self) -> None:
        if hasattr(self, "module_scope_label"):
            label = "根项目" if not self.active_module_id else f"模块：{self.active_module_id}"
            self.module_scope_label.setText(f"当前视图：{label}（双击 project.module 进入，工具栏可返回根模块）")
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        positions = self.graph.setdefault("ui", {}).setdefault("positions", {})
        visible_nodes = self.visible_nodes()
        for index, node in enumerate(visible_nodes):
            item = GraphNodeItem(node, self)
            pos = positions.get(node.get("id"), [40 + index * 30, 60 + index * 85])
            item.setPos(QPointF(float(pos[0]), float(pos[1])))
            self.scene.addItem(item)
            self.node_items[node.get("id")] = item
        self.refresh_edges()

    def refresh_edges(self) -> None:
        for edge in self.edge_items:
            self.scene.removeItem(edge)
        self.edge_items = []
        pairs = [(edge.get("from"), edge.get("to")) for edge in self.graph.get("edges", [])]
        for flow in self.graph.get("flows", []):
            if flow.get("type") == "control.line_follower":
                sensor = flow.get("sensor")
                sensor_node = self._find_node(sensor)
                pairs.extend([
                    (sensor_node.get("input") if sensor_node else self._line_input_id(), sensor),
                    (sensor, flow.get("left_motor")),
                    (sensor, flow.get("right_motor")),
                    (flow.get("pid"), flow.get("left_motor")),
                    (flow.get("pid"), flow.get("right_motor")),
                ])
        for src, dst in pairs:
            if src in self.node_items and dst in self.node_items:
                line = QGraphicsLineItem()
                src_item = self.node_items[src]
                dst_item = self.node_items[dst]
                a = src_item.sceneBoundingRect().center()
                b = dst_item.sceneBoundingRect().center()
                line.setLine(a.x(), a.y(), b.x(), b.y())
                src_type = self.node_items[src].node.get("type") if src in self.node_items else "custom.card"
                line.setPen(QPen(QColor(node_theme(src_type)["accent"]), 2))
                line.setZValue(-1)
                self.scene.addItem(line)
                self.edge_items.append(line)

    def refresh_json_editor(self) -> None:
        self.graph_json_editor.setPlainText(json.dumps(self.graph, ensure_ascii=False, indent=2))

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

    def select_node(self, node_id: str | None) -> None:
        self.current_node_id = node_id
        node = self._find_node(node_id) if node_id else None
        if not node:
            self.selected_label.setText("未选择卡片")
            self.node_json_editor.clear()
            self.property_table.setRowCount(0)
            return
        self.selected_label.setText(f"已选择: {node.get('id')} ({TYPE_LABELS.get(node.get('type'), node.get('type'))})")
        self.node_json_editor.setPlainText(json.dumps(node, ensure_ascii=False, indent=2))
        self.populate_property_form(node)

    def _find_node(self, node_id: str | None) -> dict[str, Any] | None:
        for node in self.graph.get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None

    def update_node_position(self, node_id: str | None, pos: QPointF) -> None:
        if not node_id:
            return
        self.graph.setdefault("ui", {}).setdefault("positions", {})[node_id] = [round(pos.x(), 1), round(pos.y(), 1)]
        self.refresh_json_editor()

    def add_selected_card(self) -> None:
        item = self.palette.currentItem()
        if not item:
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        node_type = item.data(role)
        if node_type not in NODE_TEMPLATES:
            return
        template = copy.deepcopy(NODE_TEMPLATES[node_type])
        base_id = template["id"]
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        suffix = 1
        new_id = base_id
        while new_id in existing:
            suffix += 1
            new_id = f"{base_id}_{suffix}"
        template["id"] = new_id
        if self.active_module_id and template.get("type") != "project.module":
            template.setdefault("module", self.active_module_id)
        self.graph.setdefault("nodes", []).append(template)
        self.graph.setdefault("ui", {}).setdefault("positions", {})[new_id] = [80, 80]
        self.current_node_id = new_id
        self.refresh_all()


    def property_choices(self, node: dict[str, Any], key: str) -> list[str]:
        node_type = node.get("type")
        by_type = lambda t: [n.get("id", "") for n in self.graph.get("nodes", []) if n.get("type") == t]
        if key == "type":
            return sorted({tpl.get("type", name) for name, tpl in NODE_TEMPLATES.items()})
        if key == "module":
            return [""] + by_type("project.module")
        if key in {"input", "hal_name"}:
            return [""] + [n.get("id", "") for n in self.graph.get("nodes", []) if str(n.get("type", "")).startswith("hal.")]
        if key in {"sensor", "source"}:
            return [""] + [n.get("id", "") for n in self.graph.get("nodes", []) if str(n.get("type", "")).startswith(("sensor.", "module."))]
        if key in {"pid", "algorithm"}:
            return [""] + [n.get("id", "") for n in self.graph.get("nodes", []) if str(n.get("type", "")).startswith("algorithm.")]
        if key in {"left_motor", "right_motor", "target"}:
            return [""] + [n.get("id", "") for n in self.graph.get("nodes", []) if str(n.get("type", "")).startswith(("actuator.", "module."))]
        if key == "topic":
            return [""] + by_type("event.topic")
        if key == "machine":
            return [""] + by_type("state.machine")
        if key in {"from", "to"} and node_type == "state.transition":
            states = [n.get("id", "") for n in self.graph.get("nodes", []) if n.get("type") == "state.state" and (not node.get("machine") or n.get("machine") == node.get("machine"))]
            return [""] + states
        if key == "hal_type":
            return ["gpio", "uart", "i2c", "spi", "adc", "pwm", "timer", "custom"]
        if key == "sensor_type":
            return ["custom", "imu", "encoder", "ultrasonic", "line_tracking"]
        if key == "actuator_type":
            return ["custom", "led", "relay", "servo", "motor"]
        if key == "loop":
            return ["while", "for"]
        return []

    def populate_property_form(self, node: dict[str, Any]) -> None:
        self.property_table.setRowCount(0)
        for key, value in node.items():
            row = self.property_table.rowCount()
            self.property_table.insertRow(row)
            self.property_table.setItem(row, 0, QTableWidgetItem(str(key)))
            choices = self.property_choices(node, str(key))
            if choices:
                combo = QComboBox()
                combo.addItems(choices)
                if str(value) not in choices:
                    combo.addItem(str(value))
                combo.setCurrentText(str(value))
                self.property_table.setCellWidget(row, 1, combo)
                self.property_table.setItem(row, 2, QTableWidgetItem("下拉选择"))
            else:
                self.property_table.setItem(row, 1, QTableWidgetItem(form_value_text(value)))
                self.property_table.setItem(row, 2, QTableWidgetItem("文本/JSON"))

    def apply_property_form(self) -> None:
        if not self.current_node_id:
            return
        node = self._find_node(self.current_node_id)
        if not node:
            return
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
            else:
                raw_value = value_item.text() if value_item else ""
            updated[key] = parse_form_value(raw_value)
        nodes = self.graph.get("nodes", [])
        for idx, item in enumerate(nodes):
            if item.get("id") == self.current_node_id:
                nodes[idx] = updated
                self.current_node_id = str(updated.get("id", self.current_node_id))
                break
        self.refresh_all()

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
                    self._add_pin_row(node.get("id", ""), f"GPIO输入[{index}]", pin.get("port", "A"), pin.get("pin", 0), "循迹/数字输入")
            elif node.get("type") == "actuator.motor":
                pwm = node.get("pwm", {})
                direction = node.get("dir_pin", {})
                self._add_pin_row(node.get("id", ""), "PWM", pwm.get("timer", 1), pwm.get("channel", 1), "电机速度")
                self._add_pin_row(node.get("id", ""), "DIR", direction.get("port", "B"), direction.get("pin", 0), "电机方向")

    def _add_pin_row(self, node_id: str, usage: str, port, pin, note: str) -> None:
        row = self.pin_table.rowCount()
        self.pin_table.insertRow(row)
        for col, value in enumerate([node_id, usage, port, pin, note]):
            self.pin_table.setItem(row, col, QTableWidgetItem(str(value)))

    def apply_pin_planner(self) -> None:
        board = self.graph.setdefault("board", {})
        board["profile"] = self.board_profile_edit.currentText().strip() or "generic-mock"
        grouped: dict[str, list[tuple[str, str, str]]] = {}
        for row in range(self.pin_table.rowCount()):
            node_id = self.pin_table.item(row, 0).text()
            usage = self.pin_table.item(row, 1).text()
            port = self.pin_table.item(row, 2).text()
            pin = self.pin_table.item(row, 3).text()
            grouped.setdefault(node_id, []).append((usage, port, pin))
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
        lines = ["Graph → Generated Code 映射", ""]
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
                target = "Graph 组织分组 / 生成注释"
            else:
                target = "custom_files / docs"
            status, note = NODE_GENERATION_STATUS.get(node_type, ("未知", "未声明生成能力"))
            lines.append(f"- {node.get('id')} [{node_type}] → {target} | {status}：{note}")
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
        for edge in edges:
            if edge.get("from") == src_id and edge.get("to") == dst_id and edge.get("from_port") == out_port and edge.get("to_port") == in_port:
                return
        edges.append({"id": f"edge_{src_id}_{dst_id}_{len(edges) + 1}", "from": src_id, "to": dst_id, "from_port": out_port, "to_port": in_port, "kind": kind})

    def callback_stubs(self) -> list[str]:
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
            if ntype in {"state.transition", "logic.if", "logic.loop"} and node.get("condition") and not has_symbol(str(node.get("condition"))):
                name = node.get("condition")
                stubs.append(f"int {name}(void) {{\n    return 0;\n}}\n")
            if ntype == "logic.if":
                for field in ["then", "else"]:
                    name = node.get(field)
                    if name and not has_symbol(str(name)):
                        stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
            if ntype == "logic.loop" and node.get("body") and not has_symbol(str(node.get("body"))):
                name = node.get("body")
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        for task in self.graph.get("tasks", []) + [n for n in self.graph.get("nodes", []) if n.get("type") == "task.periodic"]:
            name = task.get("call")
            if name and not has_symbol(str(name)):
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        return stubs

    def generate_missing_callbacks(self) -> None:
        self.apply_code_file()
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

    def refresh_validation_panel(self, show_dialog: bool = False) -> bool:
        try:
            self.apply_code_file()
            validate_graph(self.graph)
            conflicts = self.collect_pin_conflicts()
            edge_count = len(self.graph.get("edges", []))
            visual_only = [node.get("id") for node in self.graph.get("nodes", []) if NODE_GENERATION_STATUS.get(node.get("type"), ("", ""))[0] in {"可视化占位", "说明/半自动", "可视化组织", "说明"}]
            text = f"✅ Graph 校验通过：ID、引用、周期、回调函数和签名均有效。\n统一 edges: {edge_count} 条"
            if visual_only:
                text += "\n\nℹ️ 以下节点目前不是完整代码生成节点：" + ", ".join(visual_only)
            if conflicts:
                text += "\n\n⚠️ Pin Planner 冲突：\n" + "\n".join(conflicts)
            ok = not conflicts
        except Exception as exc:  # noqa: BLE001 - UI validation panel shows validator message.
            text = f"❌ Graph 校验失败：\n{exc}"
            ok = False
        self.validation_messages = [text]
        if hasattr(self, "validation_output"):
            self.validation_output.setPlainText(text)
        if show_dialog:
            if ok:
                QMessageBox.information(self, "校验通过", text)
            else:
                QMessageBox.warning(self, "校验失败", text)
        return ok

    def auto_layout(self) -> None:
        columns = {
            "project": 20,
            "hal": 250,
            "sensor": 480,
            "algorithm": 710,
            "module": 940,
            "actuator": 940,
            "event": 1170,
            "task": 1170,
            "custom": 1170,
        }
        counters = {key: 0 for key in columns}
        positions = self.graph.setdefault("ui", {}).setdefault("positions", {})
        for node in self.graph.get("nodes", []):
            family = str(node.get("type", "custom")).split(".")[0]
            x = columns.get(family, columns["custom"])
            y = 50 + counters.get(family, 0) * 110
            counters[family] = counters.get(family, 0) + 1
            positions[node.get("id")] = [x, y]
        self.refresh_all()

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
            return
        out_port = start_port if start_port.direction == "out" else target
        in_port = target if target.direction == "in" else start_port
        if not self.connect_ports(out_port, in_port):
            self.flash_invalid_connection(in_port)
            QMessageBox.warning(self, "连接无效", f"不能连接 {out_port.port_type} → {in_port.port_type}")
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
        if not self._connect_pair(src, dst):
            return False
        self.add_graph_edge(src, dst, out_port.port_type, in_port.port_type, "port")
        return True


    def connect_selected_cards(self) -> None:
        selected = [item for item in self.scene.selectedItems() if isinstance(item, GraphNodeItem)]
        if len(selected) != 2:
            QMessageBox.information(self, "Connect cards", "Select exactly two cards on the canvas, then click Connect Selected.")
            return
        a = selected[0].node
        b = selected[1].node
        if self._connect_pair(a, b):
            self.add_graph_edge(a, b, "selected", "selected", "selected")
            self.refresh_all()
            return
        if self._connect_pair(b, a):
            self.add_graph_edge(b, a, "selected", "selected", "selected")
            self.refresh_all()
            return
        QMessageBox.warning(self, "Connect cards", f"No supported connection rule for {a.get('type')} -> {b.get('type')}.")

    def _connect_pair(self, src: dict[str, Any], dst: dict[str, Any]) -> bool:
        src_type = src.get("type")
        dst_type = dst.get("type")
        if src_type == "hal.gpio_line_input" and dst_type == "sensor.line_tracking":
            dst["input"] = src.get("id")
            return True
        if src_type == "hal.custom" and dst_type == "sensor.custom":
            dst["hal_name"] = src.get("id")
            return True
        if src_type == "hal.custom" and dst_type == "actuator.custom":
            dst["hal_name"] = src.get("id")
            return True
        if src_type == "project.module" and dst_type != "project.module":
            dst["module"] = src.get("id")
            return True
        if src_type == "event.topic" and dst_type in {"event.publisher", "event.subscriber"}:
            dst["topic"] = src.get("id")
            return True
        if src_type in {"module.custom", "sensor.custom", "sensor.line_tracking"} and dst_type == "event.publisher":
            dst["source"] = src.get("id")
            return True
        if src_type == "event.subscriber" and dst_type == "module.custom":
            src["target"] = dst.get("id")
            return True
        if src_type == "state.machine" and dst_type in {"state.state", "state.transition"}:
            dst["machine"] = src.get("id")
            return True
        if src_type == "state.state" and dst_type == "state.transition":
            dst["from"] = src.get("id")
            dst["machine"] = src.get("machine", dst.get("machine"))
            return True
        if src_type == "state.transition" and dst_type == "state.state":
            src["to"] = dst.get("id")
            src["machine"] = dst.get("machine", src.get("machine"))
            return True
        if src_type in {"logic.if", "logic.loop"} and dst_type in {"task.periodic", "module.custom"}:
            dst["call"] = f"app_logic_{c_ident(src.get('id', 'logic'))}"
            return True
        if src_type == "sensor.line_tracking" and dst_type in {"algorithm.pid", "algorithm.custom"}:
            flow_id = f"{src.get('id')}_flow"
            flows = self.graph.setdefault("flows", [])
            existing = next((flow for flow in flows if flow.get("id") == flow_id), None)
            if existing is None:
                existing = {"id": flow_id, "type": "control.line_follower", "period_ms": self.graph.get("project", {}).get("tick_ms", 1)}
                flows.append(existing)
            existing["sensor"] = src.get("id")
            existing["pid"] = dst.get("id")
            if dst_type == "algorithm.custom":
                dst["io_contract"] = "efw_pid"
            motors = [node for node in self.graph.get("nodes", []) if node.get("type") == "actuator.motor"]
            if len(motors) >= 2:
                existing.setdefault("left_motor", motors[0].get("id"))
                existing.setdefault("right_motor", motors[1].get("id"))
            input_node = self._find_node(src.get("input"))
            channels = int(input_node.get("channels", 5)) if input_node else 5
            existing.setdefault("weights", [float(i) - (channels - 1) / 2.0 for i in range(channels)])
            return True
        if src_type == "actuator.motor" and dst_type == "actuator.motor":
            flows = self.graph.setdefault("flows", [])
            existing = flows[-1] if flows else {"id": "line_follower", "type": "control.line_follower"}
            if not flows:
                flows.append(existing)
            existing["left_motor"] = src.get("id")
            existing["right_motor"] = dst.get("id")
            return True
        if src_type == "custom.code" and dst_type in {"sensor.custom", "algorithm.custom", "module.custom", "actuator.custom", "hal.custom", "task.periodic"}:
            QMessageBox.information(self, "Connect cards", "Use the Code tab to implement callbacks named by the selected custom card.")
            return True
        return False

    def apply_node_json(self) -> None:
        if not self.current_node_id:
            return
        try:
            updated = json.loads(self.node_json_editor.toPlainText())
            if not isinstance(updated, dict):
                raise ValueError("card JSON must be an object")
            nodes = self.graph.get("nodes", [])
            for idx, node in enumerate(nodes):
                if node.get("id") == self.current_node_id:
                    nodes[idx] = updated
                    self.current_node_id = updated.get("id")
                    break
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "卡片 JSON 无效", str(exc))

    def delete_selected_node(self) -> None:
        if not self.current_node_id:
            return
        self.graph["nodes"] = [node for node in self.graph.get("nodes", []) if node.get("id") != self.current_node_id]
        self.graph.get("ui", {}).get("positions", {}).pop(self.current_node_id, None)
        self.current_node_id = None
        self.refresh_all()

    def select_code_file(self, row: int) -> None:
        self.current_code_index = row if row >= 0 else None
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index is None or self.current_code_index >= len(files):
            self.code_editor.clear()
            return
        self.code_editor.setPlainText(files[self.current_code_index].get("content", ""))

    def add_code_file(self) -> None:
        path, ok = QInputDialog.getText(self, "Add custom code", "Relative file path (for example app_custom.c):")
        if not ok or not path:
            return
        self.graph.setdefault("custom_files", []).append({"path": path, "content": DEFAULT_CUSTOM_C if path.endswith(".c") else ""})
        self.current_code_index = len(self.graph["custom_files"]) - 1
        self.refresh_code_list()
        self.refresh_json_editor()

    def apply_code_file(self) -> None:
        if self.current_code_index is None:
            return
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index >= len(files):
            return
        files[self.current_code_index]["content"] = self.code_editor.toPlainText()
        self.refresh_json_editor()

    def delete_code_file(self) -> None:
        if self.current_code_index is None:
            return
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index < len(files):
            del files[self.current_code_index]
        self.current_code_index = None
        self.refresh_code_list()
        self.refresh_json_editor()

    def apply_full_json(self) -> None:
        try:
            graph = json.loads(self.graph_json_editor.toPlainText())
            if not isinstance(graph, dict):
                raise ValueError("graph JSON must be an object")
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
        self.graph = templates[choice]()
        self.current_node_id = None
        self.auto_layout()

    def new_graph(self) -> None:
        self.graph_path = None
        self.graph = self.default_graph()
        self.current_node_id = None
        self.refresh_all()

    def open_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 Graph", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.current_node_id = None
        self.refresh_all()

    def save_graph(self) -> None:
        if not self.graph_path:
            self.save_graph_as()
            return
        self.apply_code_file()
        self.graph_path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.refresh_json_editor()

    def save_graph_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存 Graph", str(REPO_ROOT / "examples" / "graphs" / "line_tracking_car.json"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.save_graph()

    def generate_application(self) -> None:
        self.apply_code_file()
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出 application 目录")
        if not out_dir:
            return
        out_path = Path(out_dir)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(self.graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            preview = preview_application_files(tmp_path, out_path)
            summary = "\n".join(f"{item['status']}: {item['path']}" for item in preview[:40])
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
            QMessageBox.information(self, "已生成", f"已生成 EFW application:\n{out_path}")
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "生成失败", str(exc))


def main() -> int:
    if QApplication is None:
        print("未安装 PyQt。请安装 PyQt6 或 PyQt5 后再运行 tools/efw_visual_editor.py。", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans CJK SC", 10))
    window = VisualEditorWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
