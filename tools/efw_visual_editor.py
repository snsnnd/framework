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
    QGraphicsRectItem = object
    QMainWindow = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from efw_codegen import generate, validate_graph  # noqa: E402


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
    "module.custom": {"in": ["sensor", "algorithm"], "out": ["module"]},
    "task.periodic": {"in": ["module", "flow"]},
}

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
    "custom.card": "说明卡片",
    "custom.code": "代码卡片",
}


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
        self.setBrush(QBrush(QColor("#4fc3f7") if direction == "out" else QColor("#ffb74d")))
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
        self.setBrush(QBrush(QColor("#263238")))
        self.setPen(QPen(QColor("#80cbc4"), 2))
        title = QGraphicsSimpleTextItem(node.get("id", "node"), self)
        title.setBrush(QBrush(QColor("#ffffff")))
        bold_weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
        title.setFont(QFont("Sans", 10, bold_weight))
        title.setPos(8, 8)
        subtitle = QGraphicsSimpleTextItem(node.get("type", "unknown"), self)
        subtitle.setBrush(QBrush(QColor("#b0bec5")))
        subtitle.setPos(8, 34)
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
        self.graph = self.default_graph()
        self._build_ui()
        self.refresh_all()

    def default_graph(self) -> dict[str, Any]:
        return {
            "project": {"name": "generated_generic_embedded_app", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                copy.deepcopy(NODE_TEMPLATES["hal.custom"]),
                {**copy.deepcopy(NODE_TEMPLATES["sensor.custom"]), "id": "battery_sensor", "hal_name": "uart_debug", "read": "app_battery_sensor_read"},
                copy.deepcopy(NODE_TEMPLATES["actuator.custom"]),
                {**copy.deepcopy(NODE_TEMPLATES["module.custom"]), "id": "health_service", "module_type": "EFW_MODULE_SERVICE"},
                {**copy.deepcopy(NODE_TEMPLATES["task.periodic"]), "id": "heartbeat_100ms", "period_ms": 100, "call": "app_heartbeat_100ms"},
            ],
            "flows": [],
            "tasks": [
                {"id": "battery_sample_20ms", "type": "task.periodic", "period_ms": 20, "call": "app_battery_sample_20ms"},
            ],
            "custom_files": [
                {"path": "app_custom.c", "content": DEFAULT_CUSTOM_C},
            ],
            "ui": {
                "positions": {
                    "uart_debug": [20, 80],
                    "battery_sensor": [250, 60],
                    "status_led": [250, 180],
                    "health_service": [500, 80],
                    "heartbeat_100ms": [500, 200],
                }
            },
        }

    def _build_ui(self) -> None:
        toolbar = QToolBar("主工具栏")
        self.addToolBar(toolbar)
        toolbar.addAction("新建", self.new_graph)
        toolbar.addAction("打开", self.open_graph)
        toolbar.addAction("保存", self.save_graph)
        toolbar.addAction("另存为", self.save_graph_as)
        toolbar.addAction("实时校验", self.validate_current_graph)
        toolbar.addAction("生成", self.generate_application)
        toolbar.addAction("连接选中", self.connect_selected_cards)
        toolbar.addAction("自动布局", self.auto_layout)

        root_splitter = QSplitter()
        self.setCentralWidget(root_splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("模板库 / 组件市场"))
        self.palette = QListWidget()
        for node_type in NODE_TEMPLATES:
            QListWidgetItem(f"{TYPE_LABELS.get(node_type, node_type)}  ({node_type})", self.palette)
        left_layout.addWidget(self.palette)
        add_btn = QPushButton("添加卡片")
        add_btn.clicked.connect(self.add_selected_card)
        left_layout.addWidget(add_btn)
        root_splitter.addWidget(left)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        root_splitter.addWidget(self.view)

        right_tabs = QTabWidget()
        right_tabs.addTab(self._build_properties_tab(), "属性表单")
        right_tabs.addTab(self._build_pin_planner_tab(), "Board Profile / Pin Planner")
        right_tabs.addTab(self._build_validation_tab(), "实时校验")
        right_tabs.addTab(self._build_mapping_tab(), "生成映射")
        right_tabs.addTab(self._build_code_tab(), "代码")
        right_tabs.addTab(self._build_json_tab(), "Graph JSON")
        root_splitter.addWidget(right_tabs)
        root_splitter.setSizes([210, 650, 420])

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.selected_label = QLabel("未选择卡片")
        layout.addWidget(self.selected_label)
        self.property_table = QTableWidget(0, 2)
        self.property_table.setHorizontalHeaderLabels(["属性", "值"])
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
        self.board_profile_edit = QLineEdit("generic-mock")
        layout.addWidget(self.board_profile_edit)
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
        controls.addWidget(add_btn)
        controls.addWidget(apply_btn)
        controls.addWidget(delete_btn)
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
        self.refresh_validation_panel(show_dialog=False)
        self.select_node(self.current_node_id)

    def refresh_scene(self) -> None:
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        positions = self.graph.setdefault("ui", {}).setdefault("positions", {})
        for index, node in enumerate(self.graph.get("nodes", [])):
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
        pairs = []
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
                line.setPen(QPen(QColor("#ffca28"), 2))
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
        node_type = item.text().split("(")[-1].rstrip(")") if "(" in item.text() else item.text()
        template = copy.deepcopy(NODE_TEMPLATES[node_type])
        base_id = template["id"]
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        suffix = 1
        new_id = base_id
        while new_id in existing:
            suffix += 1
            new_id = f"{base_id}_{suffix}"
        template["id"] = new_id
        self.graph.setdefault("nodes", []).append(template)
        self.graph.setdefault("ui", {}).setdefault("positions", {})[new_id] = [80, 80]
        self.current_node_id = new_id
        self.refresh_all()


    def populate_property_form(self, node: dict[str, Any]) -> None:
        self.property_table.setRowCount(0)
        for key, value in node.items():
            row = self.property_table.rowCount()
            self.property_table.insertRow(row)
            self.property_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.property_table.setItem(row, 1, QTableWidgetItem(form_value_text(value)))

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
            if not key_item:
                continue
            key = key_item.text().strip()
            if not key:
                continue
            updated[key] = parse_form_value(value_item.text() if value_item else "")
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
            self.board_profile_edit.setText(str(board.get("profile", "generic-mock")))
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
        board["profile"] = self.board_profile_edit.text().strip() or "generic-mock"
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
            else:
                target = "custom_files / docs"
            lines.append(f"- {node.get('id')} [{node_type}] → {target}")
        for flow in self.graph.get("flows", []):
            lines.append(f"- flow:{flow.get('id')} [{flow.get('type')}] → app_bootstrap.c / bind + scheduler")
        self.mapping_output.setPlainText("\n".join(lines))

    def refresh_validation_panel(self, show_dialog: bool = False) -> bool:
        try:
            self.apply_code_file()
            validate_graph(self.graph)
            text = "✅ Graph 校验通过：ID、引用、周期、回调函数和签名均有效。"
            ok = True
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
            "hal": 20,
            "sensor": 250,
            "algorithm": 480,
            "module": 710,
            "actuator": 710,
            "task": 940,
            "custom": 940,
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
        if out_port.port_type == "hal" and in_port.port_type == "hal":
            return self._connect_pair(out_port.node_item.node, in_port.node_item.node)
        if out_port.port_type == "sensor" and in_port.port_type == "sensor":
            return self._connect_pair(out_port.node_item.node, in_port.node_item.node)
        if out_port.port_type in {"algorithm", "module"} and in_port.port_type in {"control", "module", "flow"}:
            return self._connect_pair(out_port.node_item.node, in_port.node_item.node)
        return self._connect_pair(out_port.node_item.node, in_port.node_item.node)


    def connect_selected_cards(self) -> None:
        selected = [item for item in self.scene.selectedItems() if isinstance(item, GraphNodeItem)]
        if len(selected) != 2:
            QMessageBox.information(self, "Connect cards", "Select exactly two cards on the canvas, then click Connect Selected.")
            return
        a = selected[0].node
        b = selected[1].node
        if self._connect_pair(a, b) or self._connect_pair(b, a):
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
            force = False
            if out_path.exists() and any(out_path.iterdir()):
                answer = QMessageBox.question(self, "覆盖确认", f"输出目录已存在且非空：\n{out_path}\n是否清空并重新生成？")
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
    window = VisualEditorWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
