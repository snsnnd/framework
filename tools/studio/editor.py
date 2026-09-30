#!/usr/bin/env python3
"""PyQt visual graph + code editor for the EFW application generator.

This is the second milestone of the blueprint workflow: users can create known
EFW cards visually, edit their JSON properties, write custom C/H files in the
same project, and invoke tools/efw.py codegen to export an application folder.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

import importlib.util

from studio.qt_compat import (
    QT_LIB,
    Qt, QTimer, QRectF, QPointF,
    QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence, QPen, QShortcut,
    QApplication, QFileDialog, QFormLayout, QGraphicsEllipseItem, QGraphicsItem,
    QGraphicsLineItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QPlainTextEdit, QSplitter,
    QTableWidget, QTableWidgetItem, QTabBar, QTabWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from codegen import c_ident
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
from tools.api.graph import generate_graph_application, preview_graph_generation
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

REPO_ROOT = Path(__file__).resolve().parents[2]

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

SINGLE_INPUT_PORT_RULES: dict[str, set[str]] = {
    "event.publisher": {"topic", "event_source"},
    "event.subscriber": {"topic", "event"},
    "sensor.line_tracking": {"hal"},
    "sensor.custom": {"hal"},
    "actuator.custom": {"hal", "control"},
    "algorithm.pid": {"sensor", "processor"},
    "algorithm.custom": {"sensor", "processor"},
    "processor.custom": {"sensor", "algorithm", "event", "module_input"},
    "state.machine": {"state_machine"},
    "state.transition": {"state_machine", "transition_from"},
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
from studio.editor_code import CodeEditorMixin
from studio.editor_debug import DebugMixin
from studio.editor_properties import PropertyMixin
from studio.editor_ui import UIBuilderMixin
from studio.editor_validation import ValidationMixin
from studio.editor_workbench import WorkbenchMixin
from studio.editor_shortcuts import (
    SHORTCUT_DEFAULTS, SHORTCUT_SEPARATOR, SHORTCUT_CALLBACKS,
    SHORTCUTS_CONFIG_PATH, ShortcutsEditor,
    load_custom_shortcuts, save_custom_shortcuts,
)

class VisualEditorWindow(CodeEditorMixin, PropertyMixin, ValidationMixin, CallbackMixin, WorkbenchMixin, DebugMixin, UIBuilderMixin, QMainWindow):
    def __init__(self, embedded: bool = False):
        super().__init__()
        self.embedded = embedded
        self.setWindowTitle(f"EFW 项目装配器 ({QT_LIB})")
        self.resize(1180, 720)
        self.setMinimumSize(900, 560)
        self.graph_path: Path | None = None
        self.current_node_id: str | None = None
        self.focus_node_id: str | None = None
        self.current_code_index: int | None = None
        self.node_items: dict[str, GraphNodeItem] = {}
        self.edge_items: list[QGraphicsLineItem] = []
        self.drag_line: QGraphicsLineItem | None = None
        self.drag_port: PortItem | None = None
        self.drag_target_port: PortItem | None = None
        self._drag_batch_origin: dict[str, list[float]] = {}
        self._drag_batch_anchor: str | None = None
        self.validation_messages: list[str] = []
        self.validation_targets: list[str | None] = []
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self._suspend_history = False
        self.autosave_path = REPO_ROOT / ".efw_studio_autosave.json"
        self.open_pages = [root_page()]
        self.active_page_key = "root"
        self._is_dirty = False
        self._dismissed_recovery_autosaves: set[str] = set()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(lambda: self.autosave_graph(force=True))
        self._edge_animation_timer = QTimer(self)
        self._edge_animation_timer.timeout.connect(self.tick_edge_animations)
        self._edge_animation_timer.start(70)
        self._last_output_dir: Path | None = None
        self._loaded_code_content = ""
        self._code_buffer_dirty = False
        self._suppress_code_text_events = False
        self._reverting_code_selection = False
        self.state_changed_callback = None
        self.graph = self.default_graph()
        self.setStyleSheet(WORKBENCH_STYLESHEET)
        self._build_ui()
        self._state_label = QLabel("已保存")
        self.statusBar().addPermanentWidget(self._state_label)
        self._install_shortcuts()
        self.refresh_all()
        self._check_first_run()

    def _check_first_run(self) -> None:
        """Check if this is the first run and show welcome guide."""
        guide_shown_file = REPO_ROOT / ".efw_studio_guide_shown"
        if not guide_shown_file.exists():
            # Show welcome guide after a short delay to ensure UI is ready
            QTimer.singleShot(500, self._show_welcome_guide)

    def _show_welcome_guide(self) -> None:
        """Show welcome guide and mark as shown."""
        self.show_welcome_guide()
        guide_shown_file = REPO_ROOT / ".efw_studio_guide_shown"
        guide_shown_file.write_text("shown", encoding="utf-8")

    def graph_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.graph)

    def push_undo(self) -> None:
        if self._suspend_history:
            return
        self.undo_stack.append(self.graph_snapshot())
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._mark_dirty()

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

    def _autosave_key(self) -> str:
        return str(self._autosave_for_current_graph().resolve())

    def _mark_dirty(self) -> None:
        self._is_dirty = True
        self._update_state_views()

    def schedule_autosave(self) -> None:
        if not self._is_dirty:
            return
        self._autosave_timer.start(700)
        self._update_state_views()

    def _reset_autosave_session(self) -> None:
        if hasattr(self, "_autosave_timer"):
            self._autosave_timer.stop()

    def _dirty_kinds(self) -> list[str]:
        kinds: list[str] = []
        if self._is_dirty:
            kinds.append("Graph")
        if self._code_buffer_dirty:
            kinds.append("Code")
        return kinds

    def _update_state_views(self) -> None:
        labels = self._dirty_kinds()
        text = "已保存" if not labels else "未保存：" + " / ".join(labels)
        if hasattr(self, "_state_label"):
            self._state_label.setText(text)
        title_suffix = " *" if labels else ""
        self.setWindowTitle(f"EFW 项目装配器 ({QT_LIB}){title_suffix}")
        callback = getattr(self, "state_changed_callback", None)
        if callback:
            callback()

    def code_buffer_is_dirty(self) -> bool:
        return self._code_buffer_dirty

    def _set_loaded_code_content(self, content: str) -> None:
        self._loaded_code_content = content
        self._code_buffer_dirty = False
        self._update_state_views()

    def on_code_editor_text_changed(self) -> None:
        if self._suppress_code_text_events:
            return
        self._code_buffer_dirty = self.code_editor.toPlainText() != self._loaded_code_content
        if hasattr(self, "code_status_label") and self.current_code_index is not None:
            files = self.graph.setdefault("custom_files", [])
            if self.current_code_index < len(files):
                path = files[self.current_code_index].get("path", "unnamed")
                suffix = " · 缓冲区未保存" if self._code_buffer_dirty else ""
                self.code_status_label.setText(f"{path}{suffix}")
        self._update_state_views()

    def autosave_graph(self, force: bool = False) -> None:
        if not force and not self._is_dirty:
            return
        try:
            autosave = self._autosave_for_current_graph()
            autosave.parent.mkdir(parents=True, exist_ok=True)
            autosave.write_text(
                json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            return

    def check_autosave_recovery(self) -> bool:
        """Check for an autosave file and offer to recover; return True if recovery was performed."""
        autosave = self._autosave_for_current_graph()
        autosave_key = self._autosave_key()
        if not autosave.exists():
            return False
        if autosave_key in self._dismissed_recovery_autosaves:
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
                self._dismissed_recovery_autosaves.discard(autosave_key)
                self.graph = saved_graph
                self.normalize_graph_runtime_state()
                self._is_dirty = True
                self.refresh_all()
                return True
            self._dismissed_recovery_autosaves.add(autosave_key)
        except (OSError, json.JSONDecodeError):
            autosave.unlink(missing_ok=True)
            self._dismissed_recovery_autosaves.discard(autosave_key)
        return False

    def refresh_after_change(self) -> None:
        self._mark_dirty()
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
            "create_backdrop": self.create_backdrop_from_selection,
            "delete_selected_node": self.delete_selected_object,
            "delete_selected_node2": self.delete_selected_object,
            "flip_ports": self.flip_selected_node_ports,
            "zoom_in": lambda: self.zoom_relation_view(1.15),
            "zoom_out": lambda: self.zoom_relation_view(1 / 1.15),
            "zoom_reset": self.reset_relation_zoom,
            "workspace_dashboard": lambda: self.set_workspace("项目总览"),
            "workspace_assembly": lambda: self.set_workspace("模块装配"),
            "workspace_relations": lambda: self.set_workspace("关系视图"),
            "workspace_release": lambda: self.set_workspace("生成发布"),
            "inspector_structure": lambda: self.set_right_tab("项目结构"),
            "inspector_properties": lambda: self.set_right_tab("属性表单"),
            "inspector_code": lambda: self.set_right_tab("代码补齐"),
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


    DEFAULT_CUSTOM_C = DEFAULT_CUSTOM_C

    def begin_port_drag(self, port: PortItem) -> None:
        if not self._scene_item_alive(port):
            return
        self.drag_port = port
        self.drag_line = None
        self.show_compatible_target_preview(port)

    def update_port_drag(self, pos: QPointF) -> None:
        if not self.drag_port:
            return
        if not self._scene_item_alive(self.drag_port):
            self.drag_port = None
            self.drag_target_port = None
            return
        self.show_compatible_target_preview(self.drag_port)
        target = self.port_at(pos)
        if target and target.direction != self.drag_port.direction:
            if self.drag_target_port and self.drag_target_port is not target:
                self._safe_scene_call(self.drag_target_port, "setScale", 1.0)
            self._safe_scene_call(target, "setScale", 1.55)
            self.drag_target_port = target
            return
        if self.drag_target_port:
            self._safe_scene_call(self.drag_target_port, "setScale", 1.0)
            self.drag_target_port = None

    def finish_port_drag(self, pos: QPointF, released_port: PortItem) -> None:
        start_port = self.drag_port
        self.drag_line = None
        if self.drag_target_port:
            self._safe_scene_call(self.drag_target_port, "setScale", 1.0)
        self.drag_target_port = None
        self.drag_port = None
        self.clear_compatible_target_preview()
        self.apply_focus_mode(self.focus_node_id)
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
        if not self._scene_item_alive(port):
            return
        try:
            original = port.brush()
        except RuntimeError:
            return
        if not self._safe_scene_call(port, "setBrush", QBrush(QColor("#e53935"))):
            return

        def restore_port_brush(p=port, b=original):
            self._safe_scene_call(p, "setBrush", b)

        # Reset after 1.5s so the red flash doesn't persist forever
        QTimer.singleShot(1500, restore_port_brush)

    def connect_ports(self, out_port: PortItem, in_port: PortItem) -> bool:
        src = out_port.node_item.node
        dst = in_port.node_item.node
        if not can_connect_ports(src, dst, out_port.port_type, in_port.port_type):
            return False
        if self.single_input_port_occupied(dst, in_port.port_type, exclude_from=str(src.get("id", ""))):
            return False
        # Single undo point for the entire connect operation
        self.push_undo()
        if not self._connect_pair(src, dst):
            return False
        self.add_graph_edge(src, dst, out_port.port_type, in_port.port_type, "port")
        return True

    def single_input_port_occupied(self, node: dict[str, Any], port_type: str, exclude_from: str | None = None) -> bool:
        node_type = str(node.get("type", ""))
        if port_type not in SINGLE_INPUT_PORT_RULES.get(node_type, set()):
            return False
        node_id = str(node.get("id", ""))
        for edge in self.graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if str(edge.get("to", "")) != node_id:
                continue
            if str(edge.get("to_port", "")) != port_type:
                continue
            if exclude_from and str(edge.get("from", "")) == exclude_from:
                continue
            return True
        return False

    def connection_failure_reason(self, out_port: PortItem, in_port: PortItem) -> str:
        src = out_port.node_item.node
        dst = in_port.node_item.node
        from_label = PORT_LABELS.get(out_port.port_type, out_port.port_type)
        to_label = PORT_LABELS.get(in_port.port_type, in_port.port_type)
        src_label = f"{src.get('id')} ({TYPE_LABELS.get(src.get('type'), src.get('type'))})"
        dst_label = f"{dst.get('id')} ({TYPE_LABELS.get(dst.get('type'), dst.get('type'))})"
        if src.get("id") == dst.get("id"):
            return "不能把卡片连接到自身；请连接到另一个节点。"
        if self.single_input_port_occupied(dst, in_port.port_type, exclude_from=str(src.get("id", ""))):
            return f"{dst_label} 的输入端口 {to_label}({in_port.port_type}) 只允许一条来源连线；请先删除现有连线再连接新的数据源。"
        effect = edge_effect_description(src, dst, out_port.port_type, in_port.port_type)
        if not pair_has_semantics(src, dst):
            return f"{src_label} -> {dst_label} 没有定义 Graph 语义；当前不会自动推导字段或生成代码关系。"
        return f"端口类型不兼容：{from_label}({out_port.port_type}) 不能连接到 {to_label}({in_port.port_type})。\n输出端口说明：{PORT_DESCRIPTIONS.get(out_port.port_type, '无')}\n输入端口说明：{PORT_DESCRIPTIONS.get(in_port.port_type, '无')}\n如果改用兼容端口，本关系的生成/语义效果：{effect}"


    def connect_selected_cards(self) -> None:
        QMessageBox.information(self, "端口连线", "请从卡片右侧输出端口圆点拖拽到另一张卡片左侧输入端口圆点；Studio 不再支持中心点选中连线。")

    def create_backdrop_from_selection(self) -> None:
        selected_ids = [node_id for node_id, item in self.node_items.items() if item.isSelected()]
        if not selected_ids:
            if self.current_node_id:
                selected_ids = [self.current_node_id]
            else:
                QMessageBox.information(self, "创建分组区域", "请先选择一个或多个节点，再创建分组区域。")
                return
        rects = [self.node_items[node_id].sceneBoundingRect() for node_id in selected_ids if node_id in self.node_items]
        if not rects:
            return
        left = min(rect.left() for rect in rects) - 40
        top = min(rect.top() for rect in rects) - 50
        right = max(rect.right() for rect in rects) + 40
        bottom = max(rect.bottom() for rect in rects) + 40
        backdrops = self.graph.setdefault("ui", {}).setdefault("backdrops", [])
        backdrop = {
            "id": f"backdrop_{len(backdrops) + 1}",
            "title": f"分组区域 {len(backdrops) + 1}",
            "node_ids": selected_ids,
            "rect": [round(left, 1), round(top, 1), round(right - left, 1), round(bottom - top, 1)],
        }
        self.push_undo()
        backdrops.append(backdrop)
        self.refresh_all()

    def begin_batch_drag(self, anchor_id: str | None) -> None:
        if not anchor_id or anchor_id not in self.node_items:
            self._drag_batch_origin = {}
            self._drag_batch_anchor = None
            return
        selected_ids = [node_id for node_id, item in self.node_items.items() if item.isSelected()]
        if len(selected_ids) <= 1 or anchor_id not in selected_ids:
            selected_ids = [anchor_id]
        self._drag_batch_anchor = anchor_id
        self._drag_batch_origin = {
            node_id: list(self.page_positions().get(node_id, [float(self.node_items[node_id].scenePos().x()), float(self.node_items[node_id].scenePos().y())]))
            for node_id in selected_ids
            if node_id in self.node_items
        }

    def update_node_position(self, node_id: str | None, pos: QPointF) -> None:
        if not node_id:
            return
        if self._drag_batch_anchor == node_id and node_id in self._drag_batch_origin:
            anchor_origin = self._drag_batch_origin[node_id]
            dx = pos.x() - anchor_origin[0]
            dy = pos.y() - anchor_origin[1]
            for member_id, origin in self._drag_batch_origin.items():
                self.page_positions()[member_id] = [round(origin[0] + dx, 1), round(origin[1] + dy, 1)]
                if member_id != node_id and member_id in self.node_items:
                    member = self.node_items[member_id]
                    member.blockSignals(True)
                    member.setPos(QPointF(origin[0] + dx, origin[1] + dy))
                    member.blockSignals(False)
            self.refresh_json_editor()
            return
        self.page_positions()[node_id] = [round(pos.x(), 1), round(pos.y(), 1)]
        self.refresh_json_editor()

    def finish_batch_drag(self) -> None:
        self._drag_batch_origin = {}
        self._drag_batch_anchor = None

    def apply_node_json(self) -> None:
        if not self.current_node_id:
            return
        try:
            updated = json.loads(self.node_json_editor.toPlainText())
            if not isinstance(updated, dict):
                raise ValueError("卡片 JSON 必须是对象类型，不能是数组或基本类型")
            old_id = str(self.current_node_id)
            new_id = str(updated.get("id", old_id))
            if new_id != old_id:
                raise ValueError("id 由 Studio 根据 display_name 自动生成，不能直接修改。")
            # Validate new_id same as property form does
            if new_id != c_ident(new_id):
                raise ValueError(f"ID \"{new_id}\" 不是有效的 C 标识符（仅允许字母数字下划线，不能以数字开头）")
            # Check for duplicate ID (exclude the current node itself)
            nodes = self.graph.get("nodes", [])
            if any(node.get("id") == new_id and node.get("id") != old_id for node in nodes):
                raise ValueError(f"ID \"{new_id}\" 已被另一个卡片使用，请使用唯一标识")
            self.push_undo()
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
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001 - UI needs a simple error dialog.
            QMessageBox.warning(self, "卡片 JSON 无效", str(exc))

    def delete_selected_node(self) -> None:
        selected_ids = [node_id for node_id, item in self.node_items.items() if item.isSelected()]
        if not selected_ids:
            if not self.current_node_id:
                return
            selected_ids = [self.current_node_id]
        selected_set = {str(node_id) for node_id in selected_ids if node_id}
        if not selected_set:
            return
        self.push_undo()

        # 0. Find all child nodes of selected modules/state machines/topics
        child_ids = set()
        for node in self.graph.get("nodes", []):
            node_type = str(node.get("type", ""))
            node_id = str(node.get("id", ""))
            
            # Check if this node belongs to a selected module
            parent_module = str(node.get("module") or node.get("parent") or "")
            if parent_module in selected_set:
                child_ids.add(node_id)
            
            # Check if this state/transition belongs to a selected state machine
            if node_type in {"state.state", "state.transition"}:
                machine = str(node.get("machine") or "")
                if machine in selected_set:
                    child_ids.add(node_id)
            
            # Check if this publisher/subscriber belongs to a selected topic
            if node_type in {"event.publisher", "event.subscriber"}:
                topic = str(node.get("topic") or "")
                if topic in selected_set:
                    child_ids.add(node_id)
        
        # Merge child ids into selected set
        selected_set.update(child_ids)

        # 1. Remove selected nodes and their children.
        self.graph["nodes"] = [node for node in self.graph.get("nodes", []) if str(node.get("id")) not in selected_set]

        # 2. Remove edges that reference deleted nodes.
        self.graph["edges"] = [
            edge for edge in self.graph.get("edges", [])
            if str(edge.get("from")) not in selected_set and str(edge.get("to")) not in selected_set
        ]

        # 3. Remove flows that reference deleted nodes via any reference key.
        flow_refs = {"sensor", "pid", "left_motor", "right_motor", "flow", "source", "target", "input"}
        self.graph["flows"] = [
            flow for flow in self.graph.get("flows", [])
            if not any(str(flow.get(key)) in selected_set for key in flow_refs)
        ]

        # 4. Remove tasks that reference deleted nodes or their flow.
        self.graph["tasks"] = [
            task for task in self.graph.get("tasks", [])
            if str(task.get("flow")) not in selected_set and str(task.get("call")) not in selected_set
        ]

        # 5. Clear dangling references in remaining nodes.
        reference_keys = {
            "module", "parent", "machine", "from", "to", "topic", "source", "target",
            "input", "hal_name", "comm_name", "sensor", "pid", "left_motor", "right_motor", "flow",
        }
        for node in self.graph.get("nodes", []):
            for key in reference_keys:
                if str(node.get(key)) in selected_set:
                    node[key] = ""

        # 6. Clean up UI state.
        ui = self.graph.get("ui", {})
        for node_id in selected_set:
            ui.get("positions", {}).pop(node_id, None)
            # Also clean flip state
            if "flipped_ports" in ui:
                ui["flipped_ports"].pop(node_id, None)
        for page_positions in ui.get("positions_by_page", {}).values():
            for node_id in selected_set:
                page_positions.pop(node_id, None)
        for group in ui.get("backdrops", []):
            if isinstance(group, dict):
                group["node_ids"] = [node_id for node_id in group.get("node_ids", []) if str(node_id) not in selected_set]

        self.current_node_id = None
        self.refresh_all()

    def delete_selected_edge(self) -> None:
        edge = self.selected_edge()
        if not edge:
            return
        edge_id = str(edge.get("id", ""))
        if not edge_id:
            return
        self.push_undo()
        self.graph["edges"] = [item for item in self.graph.get("edges", []) if str(item.get("id")) != edge_id]
        self.selected_edge_id = None
        self.refresh_all()

    def delete_selected_object(self) -> None:
        if self.selected_edge_id:
            self.delete_selected_edge()
            return
        self.delete_selected_node()


    def new_graph(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._reset_autosave_session()
        self.push_undo()
        self.graph_path = None
        self.graph = self.default_graph()
        self.current_node_id = None
        self._is_dirty = False
        self._set_loaded_code_content("")
        self.refresh_all()
        self._update_state_views()

    def open_graph(self) -> None:
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开 Graph", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if not path:
            return
        self._reset_autosave_session()
        self.graph_path = Path(path)
        self.push_undo()
        self.graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.normalize_graph_runtime_state()
        self.current_node_id = None
        self._is_dirty = False
        self._set_loaded_code_content("")
        # Check autosave BEFORE refresh_all — refresh_all creates a fresh autosave
        recovered = self.check_autosave_recovery()
        if not recovered:
            self.refresh_all()
        self._update_state_views()

    def _write_graph_to_disk(self, show_feedback: bool = True) -> None:
        if not self.graph_path:
            self.save_graph_as()
            return
        self._reset_autosave_session()
        self.apply_code_file(record_history=False)
        self.graph_path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._is_dirty = False
        autosave = self._autosave_for_current_graph()
        autosave.unlink(missing_ok=True)
        self._dismissed_recovery_autosaves.discard(str(autosave.resolve()))
        self.refresh_json_editor()
        self._update_state_views()
        if show_feedback:
            msg = f"已保存 Graph：{self.graph_path.name}"
            if self.embedded:
                top = self.window()
                if hasattr(top, "statusBar"):
                    top.statusBar().showMessage(msg, 4000)
            else:
                self.statusBar().showMessage(msg, 4000)

    def save_graph(self) -> None:
        if self.embedded:
            top = self.window()
            if hasattr(top, "save_project"):
                top.save_project()
                return
        self._write_graph_to_disk(show_feedback=True)

    def save_graph_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存 Graph", str(REPO_ROOT / "examples" / "graphs" / "line_tracking_car.json"), "JSON (*.json)")
        if not path:
            return
        self.graph_path = Path(path)
        self._write_graph_to_disk(show_feedback=True)

    def open_generated_output_dir(self) -> None:
        out_dir = self._last_output_dir or (REPO_ROOT / "application")
        out_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(out_dir))  # type: ignore[attr-defined]
            return
        QMessageBox.information(self, "输出目录", f"当前环境未集成文件管理器自动打开，请查看目录：\n{out_dir}")

    def generate_application(self) -> None:
        self.apply_code_file(record_history=False)
        default_dir = str(self._last_output_dir) if self._last_output_dir else str(REPO_ROOT / "application")
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出 application 目录", default_dir)
        if not out_dir:
            return
        out_path = Path(out_dir)
        self._last_output_dir = out_path
        try:
            preview = preview_graph_generation(self.graph, out_path)
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
                    return
                force = True
            generate_graph_application(self.graph, out_path, force=force)
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
