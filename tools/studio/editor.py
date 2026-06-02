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
    from PyQt6.QtCore import QMimeData, QPointF, QTimer, Qt
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
    from PyQt5.QtCore import QMimeData, QPointF, QTimer, Qt
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
from studio.editor_registry import NODE_CATEGORIES, NODE_TEMPLATES, PROPERTY_FIELD_ORDER, TYPE_LABELS
from studio.model import BOARD_PROFILES, GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS

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



# Import extracted modules
from studio.editor_canvas import (
    BlueprintView, GraphNodeItem, PortItem, TemplatePalette,
    add_wrapped_text, card_description, card_display_name,
    card_port_lines, card_ports_by_direction, compact_text,
    form_value_text, node_theme, parse_form_value,
)
from studio.editor_callbacks import CallbackMixin
from studio.editor_ui import UIBuilderMixin
from studio.editor_workbench import WorkbenchMixin
from studio.editor_shortcuts import (
    SHORTCUT_DEFAULTS, SHORTCUT_SEPARATOR, SHORTCUT_CALLBACKS,
    SHORTCUTS_CONFIG_PATH, ShortcutsEditor,
    load_custom_shortcuts, save_custom_shortcuts,
)

class VisualEditorWindow(CallbackMixin, WorkbenchMixin, UIBuilderMixin, QMainWindow):
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
        self._is_dirty = False
        self._last_output_dir: Path | None = None
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

    def _autosave_for_current_graph(self) -> Path:
        """Return a per-graph autosave path, falling back to the global autosave."""
        if self.graph_path:
            base = self.graph_path.stem
            return self.graph_path.parent / f".efw_autosave_{base}.json"
        return self.autosave_path

    def autosave_graph(self) -> None:
        try:
            self._autosave_for_current_graph().write_text(
                json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            return

    def check_autosave_recovery(self) -> bool:
        """Check for an autosave file and offer to recover; return True if recovery was performed."""
        autosave = self._autosave_for_current_graph()
        if not autosave.exists():
            return False
        if self.graph_path and autosave.stat().st_mtime <= self.graph_path.stat().st_mtime:
            return False  # autosave is older than the saved file
        try:
            saved_graph = json.loads(autosave.read_text(encoding="utf-8"))
            if not isinstance(saved_graph, dict) or not saved_graph.get("nodes"):
                return False
            answer = QMessageBox.question(
                self, "自动恢复",
                f"检测到未保存的更改：\n{autosave.name}\n\n上次编辑时间可能晚于已保存文件。\n是否恢复未保存的更改？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            yes = QMessageBox.StandardButton.Yes
            if answer == yes:
                self.graph = saved_graph
                self._is_dirty = True
                self.refresh_all()
                return True
        except (OSError, json.JSONDecodeError):
            autosave.unlink(missing_ok=True)
        return False

    def refresh_after_change(self) -> None:
        self._is_dirty = True
        self.autosave_graph()
        self.refresh_all()

    def _confirm_discard_changes(self) -> bool:
        """Return True if it is safe to discard current graph changes."""
        if not self._is_dirty:
            return True
        answer = QMessageBox.question(
            self, "未保存的更改",
            "当前图有未保存的更改，是否保存后再继续？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        yes = QMessageBox.StandardButton.Yes
        save_btn = QMessageBox.StandardButton.Save
        discard_btn = QMessageBox.StandardButton.Discard
        if answer == save_btn:
            self.save_graph()
            return True
        if answer == discard_btn:
            return True
        return False

    def closeEvent(self, event: Any) -> None:
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    def _shortcut_callbacks(self) -> dict[str, Any]:
        """Return the mapping from shortcut key → callable, populated once."""
        global SHORTCUT_CALLBACKS
        if SHORTCUT_CALLBACKS:
            return SHORTCUT_CALLBACKS
        SHORTCUT_CALLBACKS = {
            "new_graph": self.new_graph,
            "open_graph": self.open_graph,
            "save_graph": self.save_graph,
            "save_graph_as": self.save_graph_as,
            "undo": self.undo,
            "redo": self.redo,
            "generate_application": self.generate_application,
            "add_selected_card": self.add_selected_card,
            "delete_selected_node": self.delete_selected_node,
            "delete_selected_node2": self.delete_selected_node,
            "zoom_in": lambda: self.zoom_relation_view(1.15),
            "zoom_out": lambda: self.zoom_relation_view(1 / 1.15),
            "zoom_reset": self.reset_relation_zoom,
            "workspace_dashboard": lambda: self.set_workspace("项目总览"),
            "workspace_assembly": lambda: self.set_workspace("模块装配"),
            "workspace_relations": lambda: self.set_workspace("关系视图"),
            "workspace_release": lambda: self.set_workspace("生成发布"),
            "inspector_structure": lambda: self.set_right_tab("项目结构"),
            "inspector_properties": lambda: self.set_right_tab("属性表单"),
            "inspector_code": lambda: self.set_right_tab("代码"),
            "inspector_validation": lambda: self.set_right_tab("实时校验"),
            "inspector_mapping": lambda: self.set_right_tab("生成映射"),
            "inspector_file_tree": lambda: self.set_right_tab("文件树预览"),
            "inspector_schedule": lambda: self.set_right_tab("任务调度"),
            "inspector_pin_planner": lambda: self.set_right_tab("Board Profile / Pin Planner"),
            "inspector_graph_json": lambda: self.set_right_tab("Graph JSON"),
            "validate_current_graph": self.validate_current_graph,
            "exit_module": self.exit_module,
        }
        return SHORTCUT_CALLBACKS

    def _install_shortcuts(self) -> None:
        # Clear any previously installed shortcuts
        for old in getattr(self, "shortcuts", []):
            if hasattr(old, "setEnabled"):
                old.setEnabled(False)
        self.shortcuts: list[Any] = []
        custom = load_custom_shortcuts()
        callbacks = self._shortcut_callbacks()
        for key, (label, default_seq) in SHORTCUT_DEFAULTS.items():
            if key == SHORTCUT_SEPARATOR or not label:
                continue
            seq = custom.get(key, default_seq)
            if not seq:
                continue
            cb = callbacks.get(key)
            if cb is None:
                continue
            # Support combo/chord shortcuts: user enters "Ctrl+K Ctrl+S" (space-separated)
            # QKeySequence expects "Ctrl+K, Ctrl+S" (comma-separated) for true chords.
            # Single-key shortcuts (like "Delete", "F5", "Esc") pass through unchanged.
            if " " in seq and "," not in seq:
                # Convert space-separated chord to comma-separated for QKeySequence
                qt_seq = seq.replace(" ", ", ")
            else:
                qt_seq = seq
            shortcut = QShortcut(QKeySequence(qt_seq), self)
            shortcut.activated.connect(cb)
            self.shortcuts.append(shortcut)

    def open_shortcuts_editor(self) -> None:
        custom = load_custom_shortcuts()
        dialog = ShortcutsEditor(self, custom, self._on_shortcuts_changed)
        dialog.show()

    def _on_shortcuts_changed(self, custom: dict[str, str]) -> None:
        # Uninstall old shortcuts and reinstall with new bindings
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
        self.shortcuts.clear()
        self._install_shortcuts()
        QMessageBox.information(self, "快捷键已更新", "快捷键已重新绑定，立即生效。")

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
        # Validate BEFORE push_undo to avoid useless undo entries on failure
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
        # All validation passed — now safe to push undo and apply
        self.push_undo()
        if new_id != old_id:
            self.rename_node_references(old_id, new_id)
        nodes = self.graph.get("nodes", [])
        for idx, item in enumerate(nodes):
            if item.get("id") == old_id:
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

    def edit_board_profile(self) -> None:
        """Open a dialog to add, edit, or remove Board Profiles in-Studio."""
        from studio.model import BOARD_PROFILES as _bp, REPO_ROOT as _root
        profile_path = _root / "examples" / "board_profiles" / "board_profiles.json"

        dialog = QWidget(None, Qt.WindowType.Window if hasattr(Qt, "WindowType") else Qt.Window)
        dialog.setWindowTitle("编辑 Board Profile")
        dialog.resize(500, 420)
        dlg_layout = QVBoxLayout(dialog)

        dlg_layout.addWidget(QLabel("Board Profile 数据库（JSON 格式）：\n保存到 examples/board_profiles/board_profiles.json"))
        editor = QPlainTextEdit()
        editor.setPlainText(json.dumps(dict(_bp), ensure_ascii=False, indent=2))
        dlg_layout.addWidget(editor)

        hint = QLabel("格式：{\"profile-key\": {\"label\": \"显示名\", \"ports\": [\"A\",\"B\"], \"pins_per_port\": 16, \"timers\": [1,2], \"pwm_channels\": [1,2,3,4], \"notes\": \"备注\"}}")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8f9db2; font-size: 9pt;")
        dlg_layout.addWidget(hint)

        buttons = QHBoxLayout()
        save_btn = QPushButton("保存并刷新")
        save_btn.clicked.connect(lambda: self._save_board_profiles(editor.toPlainText(), profile_path, dialog))
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.close)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        dlg_layout.addLayout(buttons)
        dialog.show()

    def _save_board_profiles(self, text: str, path: Path, dialog: QWidget) -> None:
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("必须是 JSON 对象")
            for key, profile in data.items():
                if not isinstance(profile, dict):
                    raise ValueError(f"\"{key}\" 的值必须是对象")
                if "ports" not in profile:
                    raise ValueError(f"\"{key}\" 缺少 ports 字段")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            import studio.model as _model
            _model.BOARD_PROFILES = data
            self.board_profile_edit.clear()
            self.board_profile_edit.addItems(list(data))
            QMessageBox.information(self, "Board Profile", f"已保存 {len(data)} 个 Board Profile 到：\n{path}")
            dialog.close()
        except Exception as exc:
            QMessageBox.warning(self, "格式错误", f"Board Profile JSON 无效：{exc}")

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

    def runtime_dataflow_preview_paths(self) -> list[list[str]]:
        """Mirror codegen's automatic dataflow discovery for the schedule preview."""
        nodes_by_id = {node.get("id"): node for node in self.graph.get("nodes", []) if node.get("id")}
        runtime_types = {
            "sensor.custom",
            "sensor.line_tracking",
            "processor.custom",
            "algorithm.pid",
            "algorithm.custom",
            "actuator.motor",
            "actuator.custom",
        }
        flow_owned: set[str] = set()
        for flow in self.graph.get("flows", []):
            if flow.get("type") == "control.line_follower":
                flow_owned.update(
                    str(flow.get(key))
                    for key in ("sensor", "pid", "left_motor", "right_motor")
                    if flow.get(key)
                )
        include_flow_owned = bool(self.graph.get("project", {}).get("auto_dataflow_include_line_follower", False))
        adjacency: dict[str, list[str]] = {}
        for edge in self.graph.get("edges", []):
            if edge.get("kind", "generic") not in {"data_flow", "control_flow"}:
                continue
            src = nodes_by_id.get(edge.get("from"))
            dst = nodes_by_id.get(edge.get("to"))
            if not src or not dst:
                continue
            if src.get("type") not in runtime_types or dst.get("type") not in runtime_types:
                continue
            if not include_flow_owned and (src["id"] in flow_owned or dst["id"] in flow_owned):
                continue
            adjacency.setdefault(src["id"], []).append(dst["id"])

        starts = [
            str(node["id"])
            for node in self.graph.get("nodes", [])
            if node.get("type") in {"sensor.custom", "sensor.line_tracking"} and node.get("id") in adjacency
        ]
        paths: list[list[str]] = []

        def walk(node_id: str, path: list[str], seen: set[str]) -> None:
            next_ids = [item for item in adjacency.get(node_id, []) if item not in seen]
            if not next_ids:
                if len(path) > 1:
                    paths.append(path[:])
                return
            for next_id in next_ids:
                walk(next_id, path + [next_id], seen | {next_id})

        for start in starts:
            walk(start, [start], {start})

        unique: list[list[str]] = []
        seen_keys: set[tuple[str, ...]] = set()
        for path in paths:
            key = tuple(path)
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(path)
        return unique

    def runtime_plan_preview(self) -> dict[int, list[tuple[int, str]]]:
        tick = int(self.graph.get("project", {}).get("tick_ms", 1))
        nodes_by_id = {node.get("id"): node for node in self.graph.get("nodes", []) if node.get("id")}
        plan: dict[int, list[tuple[int, str]]] = {}

        def add(period: int, order: int, label: str) -> None:
            plan.setdefault(max(int(period or tick), tick), []).append((order, label))

        for index, path in enumerate(self.runtime_dataflow_preview_paths(), start=1):
            period = max(int(nodes_by_id.get(node_id, {}).get("period_ms", tick) or tick) for node_id in path)
            names = [c_ident(node_id) for node_id in path]
            fn = "app_dataflow_" + "_".join(names[:4])
            if len(names) > 4:
                fn += f"_{index}"
            add(period, 1, f"{fn}()    # 自动 dataflow: {' → '.join(path)}")

        task_owned_flows: set[str] = {str(task.get("flow")) for task in self.graph.get("tasks", []) if task.get("flow")}
        for node in self.graph.get("nodes", []):
            if node.get("type") == "task.periodic" and node.get("flow"):
                task_owned_flows.add(str(node.get("flow")))
        for flow in self.graph.get("flows", []):
            if flow.get("type") != "control.line_follower" or flow.get("id") in task_owned_flows:
                continue
            add(int(flow.get("period_ms", tick) or tick), 2, f"efw_line_follower_update({flow.get('id')})")

        for task in self.graph.get("tasks", []):
            target = f"{task.get('call')}()" if task.get("call") else f"flow:{task.get('flow')}"
            add(int(task.get("period_ms", tick) or tick), 3, f"task {task.get('id')} → {target}")
        for node in self.graph.get("nodes", []):
            if node.get("type") == "task.periodic":
                target = f"{node.get('call')}()" if node.get("call") else f"flow:{node.get('flow')}"
                add(int(node.get("period_ms", tick) or tick), 3, f"task node {node.get('id')} → {target}")

        machine_ids = sorted(str(node.get("id")) for node in self.graph.get("nodes", []) if node.get("type") == "state.machine" and node.get("id"))
        for machine_id in machine_ids:
            add(tick, 4, f"app_{c_ident(machine_id)}_tick()")
        if any(node.get("type") == "module.custom" for node in self.graph.get("nodes", [])):
            add(tick, 5, "efw_module_poll_all()")
        return plan

    def refresh_schedule_view(self) -> None:
        if not hasattr(self, "schedule_output"):
            return
        tick = int(self.graph.get("project", {}).get("tick_ms", 1))
        lines = [f"运行计划预览（tick = {tick} ms）", ""]
        plan = self.runtime_plan_preview()
        if plan:
            for period in sorted(plan):
                lines.append(f"{period}ms:")
                for order, label in sorted(plan[period], key=lambda item: (item[0], item[1])):
                    lines.append(f"  {order}. {label}")
                lines.append("")
        else:
            lines.append("暂无自动 dataflow、flow、task、state machine 或 module poll。")
            lines.append("")
        lines.append("调度语义：")
        lines.append("  1. 自动 dataflow pipelines")
        lines.append("  2. 未被 task.periodic 接管的 control.line_follower flows")
        lines.append("  3. task.periodic")
        lines.append("  4. state.machine tick")
        lines.append("  5. efw_module_poll_all()")
        lines.append("说明：同一周期按编号顺序生成；多个 dataflow 仅按发现顺序执行，不表达跨 pipeline 依赖。")
        lines.append("如果需要严格顺序、共享状态仲裁或避免 task/module 重复处理，请收敛到 task.periodic 或 module.custom.poll。")
        self.schedule_output.setPlainText("\n".join(lines).rstrip())

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
        """Add an edge to the graph. Caller is responsible for `push_undo()` before calling."""
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
        edges.append({"id": f"edge_{src_id}_{dst_id}_{len(edges) + 1}", "from": src_id, "to": dst_id, "from_port": out_port, "to_port": in_port, "kind": kind})

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
        # Clean up any previous drag line (e.g. from rapid double-click)
        if self.drag_line:
            self.scene.removeItem(self.drag_line)
            self.drag_line = None
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
            return
        self.refresh_all()

    def port_at(self, pos: QPointF) -> PortItem | None:
        for item in self.scene.items(pos):
            if isinstance(item, PortItem):
                return item
        return None

    def flash_invalid_connection(self, port: PortItem) -> None:
        original = port.brush()
        port.setBrush(QBrush(QColor("#e53935")))
        # Reset after 1.5s so the red flash doesn't persist forever
        QTimer.singleShot(1500, lambda p=port, b=original: p.setBrush(b) if not p.scene() is None else None)

    def connect_ports(self, out_port: PortItem, in_port: PortItem) -> bool:
        src = out_port.node_item.node
        dst = in_port.node_item.node
        if not can_connect_ports(src, dst, out_port.port_type, in_port.port_type):
            return False
        # Single undo point for the entire connect operation
        self.push_undo()
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
        connected = apply_pair_semantics(src, dst, self.graph, c_ident_func=c_ident, overwrite=True)
        if connected and src.get("type") == "custom.code":
            QMessageBox.information(self, "Connect cards", "Use the Code tab to implement callbacks named by the selected custom card.")
        return connected

    def apply_node_json(self) -> None:
        if not self.current_node_id:
            return
        try:
            updated = json.loads(self.node_json_editor.toPlainText())
            if not isinstance(updated, dict):
                raise ValueError("卡片 JSON 必须是对象类型，不能是数组或基本类型")
            old_id = str(self.current_node_id)
            new_id = str(updated.get("id", old_id))
            # Validate new_id same as property form does
            if new_id != c_ident(new_id):
                raise ValueError(f"ID \"{new_id}\" 不是有效的 C 标识符（仅允许字母数字下划线，不能以数字开头）")
            # Check for duplicate ID (exclude the current node itself)
            nodes = self.graph.get("nodes", [])
            if any(node.get("id") == new_id and node.get("id") != old_id for node in nodes):
                raise ValueError(f"ID \"{new_id}\" 已被另一个卡片使用，请使用唯一标识")
            if new_id != old_id:
                self.rename_node_references(old_id, new_id)
            # Find by old_id only (not or-condition) to avoid matching wrong node
            for idx, node in enumerate(nodes):
                if node.get("id") == old_id:
                    nodes[idx] = updated
                    self.current_node_id = new_id
                    break
            else:
                raise ValueError(f"找不到 ID 为 \"{old_id}\" 的节点，可能已被删除")
            self.push_undo()
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "卡片 JSON 无效", str(exc))

    def delete_selected_node(self) -> None:
        if not self.current_node_id:
            return
        self.push_undo()
        node_id = self.current_node_id

        # 1. Remove the node itself.
        self.graph["nodes"] = [node for node in self.graph.get("nodes", []) if node.get("id") != node_id]

        # 2. Remove edges that reference the deleted node.
        self.graph["edges"] = [
            edge for edge in self.graph.get("edges", [])
            if edge.get("from") != node_id and edge.get("to") != node_id
        ]

        # 3. Remove flows that reference the deleted node via any reference key.
        flow_refs = {"sensor", "pid", "left_motor", "right_motor", "flow", "source", "target", "input"}
        self.graph["flows"] = [
            flow for flow in self.graph.get("flows", [])
            if not any(flow.get(key) == node_id for key in flow_refs)
        ]

        # 4. Remove tasks that reference the deleted node or its flow.
        self.graph["tasks"] = [
            task for task in self.graph.get("tasks", [])
            if task.get("flow") != node_id and task.get("call") != node_id
        ]

        # 5. Clear dangling references in remaining nodes.
        reference_keys = {
            "module", "parent", "machine", "from", "to", "topic", "source", "target",
            "input", "hal_name", "comm_name", "sensor", "pid", "left_motor", "right_motor", "flow",
        }
        for node in self.graph.get("nodes", []):
            for key in reference_keys:
                if node.get(key) == node_id:
                    node[key] = ""

        # 6. Clean up UI state.
        ui = self.graph.get("ui", {})
        ui.get("positions", {}).pop(node_id, None)
        for page_positions in ui.get("positions_by_page", {}).values():
            page_positions.pop(node_id, None)

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
        """Simple C code formatter: protect strings and comments, normalise whitespace and braces."""
        protected: list[str] = []

        def protect(match: Any) -> str:
            protected.append(match.group(0))
            return f"__PROTECTED_{len(protected) - 1}__"

        import re
        text = text.replace("\r\n", "\n").replace("\t", "  ")
        # Protect in order: comments first, then string literals (so comments inside strings don't break)
        text = re.sub(r"/\*.*?\*/", protect, text, flags=re.S)
        text = re.sub(r"//[^\n]*", protect, text)
        text = re.sub(r'"(?:[^"\\]|\\.)*"', protect, text)
        text = re.sub(r"'(?:[^'\\]|\\.)'", protect, text)
        # Normalise braces and semicolons
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

        result: list[str] = []
        indent = 0
        previous_blank = False
        for line in raw_lines:
            if not line.startswith("__PROTECTED_") and not line:
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
                if result and not result[-1].strip().startswith("#") and not result[-1].strip().startswith("__PROTECTED_"):
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
            formatted = formatted.replace(f"__PROTECTED_{index}__", comment)
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
        answer = QMessageBox.question(
            self, "确认覆盖",
            "确定要用 JSON 编辑器内容替换整个 Graph 吗？\n\n此操作会直接覆盖所有节点、连线和设置（可通过撤销恢复）。\n建议先用 Ctrl+S 保存当前 Graph 再操作。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        yes = QMessageBox.StandardButton.Yes
        if answer != yes:
            return
        try:
            graph = json.loads(self.graph_json_editor.toPlainText())
            if not isinstance(graph, dict):
                raise ValueError("Graph JSON 必须是对象类型，不能是数组或基本类型")
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
            "空白画布（从零开始）": lambda: {"project": {"name": "blank_project", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}], "ui": {"positions": {}}},
            "空白多模块项目": lambda: {"project": {"name": "new_modular_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}], "ui": {"positions": {"control_module": [40, 40]}}},
            "状态机项目": lambda: {"project": {"name": "state_machine_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"]), copy.deepcopy(NODE_TEMPLATES["state.machine"]), copy.deepcopy(NODE_TEMPLATES["state.state"]), copy.deepcopy(NODE_TEMPLATES["state.transition"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}], "ui": {"positions": {}}},
        }
        choice, ok = QInputDialog.getItem(self, "项目向导", "选择模板", list(templates), 0, False)
        if not ok or not choice:
            return
        if not self._confirm_discard_changes():
            return
        self.graph_path = None
        self.push_undo()
        self.graph = templates[choice]()
        self.current_node_id = None
        self._is_dirty = False
        self.refresh_all()

    def new_graph(self) -> None:
        if not self._confirm_discard_changes():
            return
        self.push_undo()
        self.graph_path = None
        self.graph = self.default_graph()
        self.current_node_id = None
        self._is_dirty = False
        self.refresh_all()

    def open_graph(self) -> None:
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开 Graph", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.push_undo()
        self.graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.current_node_id = None
        self._is_dirty = False
        # Check autosave BEFORE refresh_all — refresh_all creates a fresh autosave
        recovered = self.check_autosave_recovery()
        if not recovered:
            self.refresh_all()

    def save_graph(self) -> None:
        if not self.graph_path:
            self.save_graph_as()
            return
        self.apply_code_file(record_history=False)
        self.graph_path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._is_dirty = False
        self.refresh_json_editor()
        # Content is safely on disk — delete the autosave so it won't trigger a false recovery prompt
        self._autosave_for_current_graph().unlink(missing_ok=True)
        # Show save confirmation on the visible status bar
        msg = f"已保存 Graph：{self.graph_path.name}"
        if self.embedded:
            # Embedded in manager — status bar is on the top-level window
            top = self.window()
            if hasattr(top, "statusBar"):
                top.statusBar().showMessage(msg, 4000)
        else:
            self.statusBar().showMessage(msg, 4000)

    def save_graph_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存 Graph", str(REPO_ROOT / "examples" / "graphs" / "line_tracking_car.json"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self.save_graph()

    def generate_application(self) -> None:
        self.apply_code_file(record_history=False)
        default_dir = str(self._last_output_dir) if self._last_output_dir else str(REPO_ROOT / "application")
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出 application 目录", default_dir)
        if not out_dir:
            return
        out_path = Path(out_dir)
        self._last_output_dir = out_path
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
