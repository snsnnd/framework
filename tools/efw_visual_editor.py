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
        QPushButton,
        QPlainTextEdit,
        QSplitter,
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
        QPushButton,
        QPlainTextEdit,
        QSplitter,
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

efw_status_t app_custom_sensor_read(void *ctx, void *out) {
    EFW_UNUSED(ctx);
    EFW_UNUSED(out);
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
"""


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
        self.setWindowTitle(f"EFW Visual Editor ({QT_LIB})")
        self.resize(1280, 760)
        self.graph_path: Path | None = None
        self.current_node_id: str | None = None
        self.current_code_index: int | None = None
        self.node_items: dict[str, GraphNodeItem] = {}
        self.edge_items: list[QGraphicsLineItem] = []
        self.graph = self.default_graph()
        self._build_ui()
        self.refresh_all()

    def default_graph(self) -> dict[str, Any]:
        return {
            "project": {"name": "generated_line_tracking_car", "tick_ms": 1},
            "nodes": [
                copy.deepcopy(NODE_TEMPLATES["hal.gpio_line_input"]),
                copy.deepcopy(NODE_TEMPLATES["sensor.line_tracking"]),
                {**copy.deepcopy(NODE_TEMPLATES["actuator.motor"]), "id": "left_motor"},
                {**copy.deepcopy(NODE_TEMPLATES["actuator.motor"]), "id": "right_motor", "pwm": {"timer": 1, "channel": 2}, "dir_pin": {"port": "B", "pin": 1}},
                copy.deepcopy(NODE_TEMPLATES["algorithm.pid"]),
            ],
            "flows": [copy.deepcopy(DEFAULT_FLOW)],
            "custom_files": [
                {"path": "app_custom.c", "content": DEFAULT_CUSTOM_C},
            ],
            "ui": {
                "positions": {
                    "line_input": [20, 80],
                    "line_sensor_5ch": [240, 80],
                    "line_pid": [240, 210],
                    "left_motor": [500, 40],
                    "right_motor": [500, 170],
                }
            },
        }

    def _build_ui(self) -> None:
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        toolbar.addAction("New", self.new_graph)
        toolbar.addAction("Open", self.open_graph)
        toolbar.addAction("Save", self.save_graph)
        toolbar.addAction("Save As", self.save_graph_as)
        toolbar.addAction("Validate", self.validate_current_graph)
        toolbar.addAction("Generate", self.generate_application)

        root_splitter = QSplitter()
        self.setCentralWidget(root_splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Card Palette"))
        self.palette = QListWidget()
        for node_type in NODE_TEMPLATES:
            QListWidgetItem(node_type, self.palette)
        left_layout.addWidget(self.palette)
        add_btn = QPushButton("Add Card")
        add_btn.clicked.connect(self.add_selected_card)
        left_layout.addWidget(add_btn)
        root_splitter.addWidget(left)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        root_splitter.addWidget(self.view)

        right_tabs = QTabWidget()
        right_tabs.addTab(self._build_properties_tab(), "Properties")
        right_tabs.addTab(self._build_code_tab(), "Code")
        right_tabs.addTab(self._build_json_tab(), "Graph JSON")
        root_splitter.addWidget(right_tabs)
        root_splitter.setSizes([210, 650, 420])

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.selected_label = QLabel("No card selected")
        self.node_json_editor = QPlainTextEdit()
        apply_btn = QPushButton("Apply Card JSON")
        apply_btn.clicked.connect(self.apply_node_json)
        delete_btn = QPushButton("Delete Card")
        delete_btn.clicked.connect(self.delete_selected_node)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.node_json_editor)
        layout.addWidget(apply_btn)
        layout.addWidget(delete_btn)
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
            self.selected_label.setText("No card selected")
            self.node_json_editor.clear()
            return
        self.selected_label.setText(f"Selected: {node.get('id')} ({node.get('type')})")
        self.node_json_editor.setPlainText(json.dumps(node, ensure_ascii=False, indent=2))

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
        template = copy.deepcopy(NODE_TEMPLATES[item.text()])
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
            QMessageBox.warning(self, "Invalid card JSON", str(exc))

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
            QMessageBox.warning(self, "Invalid graph JSON", str(exc))

    def validate_current_graph(self) -> bool:
        try:
            self.apply_code_file()
            validate_graph(self.graph)
            QMessageBox.information(self, "Graph valid", "Graph is valid for the current MVP generator.")
            return True
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "Graph invalid", str(exc))
            return False

    def new_graph(self) -> None:
        self.graph_path = None
        self.graph = self.default_graph()
        self.current_node_id = None
        self.refresh_all()

    def open_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open graph", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
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
        path, _ = QFileDialog.getSaveFileName(self, "Save graph", str(REPO_ROOT / "examples" / "graphs" / "line_tracking_car.json"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.save_graph()

    def generate_application(self) -> None:
        self.apply_code_file()
        out_dir = QFileDialog.getExistingDirectory(self, "Select output application directory")
        if not out_dir:
            return
        out_path = Path(out_dir)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(self.graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            generate(tmp_path, out_path, force=True)
            tmp_path.unlink(missing_ok=True)
            QMessageBox.information(self, "Generated", f"Generated EFW application:\n{out_path}")
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "Generate failed", str(exc))


def main() -> int:
    if QApplication is None:
        print("PyQt is not installed. Install PyQt6 or PyQt5, then run tools/efw_visual_editor.py.", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    window = VisualEditorWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
