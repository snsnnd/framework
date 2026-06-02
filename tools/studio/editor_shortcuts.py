#!/usr/bin/env python3
"""Keyboard shortcuts system for the EFW visual editor."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeySequence, QShortcut
    from PyQt6.QtWidgets import (
        QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import (
        QHBoxLayout, QLabel, QPushButton, QShortcut, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QWidget = QTableWidget = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[2]


def shortcuts_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "efw" / "studio_shortcuts.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "efw" / "studio_shortcuts.json"
    return Path.home() / ".config" / "efw" / "studio_shortcuts.json"

SHORTCUT_DEFAULTS: dict[str, tuple[str, str]] = {
    # (display_name, default_key_sequence)
    "new_graph":              ("新建 Graph", "Ctrl+N"),
    "open_graph":             ("打开 Graph", "Ctrl+O"),
    "save_graph":             ("保存 Graph", "Ctrl+S"),
    "save_graph_as":          ("另存为 Graph", "Ctrl+Shift+S"),
    "undo":                   ("撤销", "Ctrl+Z"),
    "redo":                   ("重做", "Ctrl+Y"),
    "generate_application":   ("生成 Application", "Ctrl+G"),
    "add_selected_card":      ("添加选中卡片", "Ctrl+M"),
    "delete_selected_node":   ("删除选中卡片", "Delete"),
    "delete_selected_node2":  ("删除选中卡片 (Backspace)", "Backspace"),
    "zoom_in":                ("放大画布", "Ctrl++"),
    "zoom_out":               ("缩小画布", "Ctrl+-"),
    "zoom_reset":             ("重置缩放", "Ctrl+0"),
    "workspace_dashboard":    ("工作区：项目总览", "Ctrl+1"),
    "workspace_assembly":     ("工作区：模块装配", "Ctrl+2"),
    "workspace_relations":    ("工作区：关系视图", "Ctrl+3"),
    "workspace_release":      ("工作区：生成发布", "Ctrl+4"),
    "inspector_structure":    ("Inspector：项目结构", "Alt+1"),
    "inspector_properties":   ("Inspector：属性表单", "Alt+2"),
    "inspector_code":         ("Inspector：代码", "Alt+3"),
    "inspector_validation":   ("Inspector：实时校验", "Alt+4"),
    "inspector_mapping":      ("Inspector：生成映射", "Alt+5"),
    "inspector_file_tree":    ("Inspector：文件树预览", "Alt+6"),
    "inspector_schedule":     ("Inspector：任务调度", "Alt+7"),
    "inspector_pin_planner":  ("Inspector：Board Profile", "Alt+8"),
    "inspector_graph_json":   ("Inspector：Graph JSON", "Alt+9"),
    "validate_current_graph": ("校验 Graph", "F5"),
    "exit_module":            ("返回根项目", "Esc"),
    "undo_skip":              ("", ""),  # sentinel separator
}
SHORTCUT_SEPARATOR = "undo_skip"

SHORTCUT_CALLBACKS: dict[str, Any] = {}  # populated at install time

SHORTCUTS_CONFIG_PATH = shortcuts_config_path()
LEGACY_SHORTCUTS_CONFIG_PATH = REPO_ROOT / ".efw_shortcuts.json"


def load_custom_shortcuts() -> dict[str, str]:
    for path in (SHORTCUTS_CONFIG_PATH, LEGACY_SHORTCUTS_CONFIG_PATH):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, str) and v}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_custom_shortcuts(mapping: dict[str, str]) -> None:
    try:
        SHORTCUTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHORTCUTS_CONFIG_PATH.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


class ShortcutsEditor(QWidget):
    """Standalone dialog for viewing and editing keyboard shortcuts with combo-key support."""

    def __init__(self, parent: Any, current_shortcuts: dict[str, str],
                 on_changed: Any):
        super().__init__(parent if hasattr(QWidget, "__init__") else None)
        if QWidget is object:
            return
        # Use QDialog wrapper if parent is set
        self._parent = parent
        self._on_changed = on_changed
        self._capture_mode = False
        self._capture_key: str | None = None
        self._capture_keys: list[int] = []
        self._capture_button: QPushButton | None = None
        self.setWindowTitle("快捷键设定")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("双击或点击「编辑」修改快捷键。支持组合快捷键（如 Ctrl+K Ctrl+S），按 Esc 取消捕获。"))
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["操作", "当前快捷键", ""])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 240)
        self._table.setColumnWidth(1, 170)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows if hasattr(QTableWidget, "SelectionBehavior") else QTableWidget.SelectRows)
        layout.addWidget(self._table)
        self._build_rows(current_shortcuts)
        buttons = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(lambda: self._build_rows({}))
        save_btn = QPushButton("保存并关闭")
        save_btn.clicked.connect(self._save_and_close)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def _build_rows(self, custom: dict[str, str]) -> None:
        self._table.setRowCount(0)
        self._row_keys: list[str] = []
        row = 0
        for key, (label, default_seq) in SHORTCUT_DEFAULTS.items():
            if key == SHORTCUT_SEPARATOR:
                continue
            if not label:
                continue
            current = custom.get(key, default_seq)
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, QTableWidgetItem(current))
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(self._make_capture(row, edit_btn))
            self._table.setCellWidget(row, 2, edit_btn)
            self._row_keys.append(key)
            row += 1

    def _make_capture(self, row: int, button: QPushButton) -> Any:
        def start():
            if self._capture_mode:
                return
            self._capture_mode = True
            self._capture_key = self._row_keys[row]
            self._capture_keys = []
            self._capture_button = button
            button.setText("按下快捷键… (Esc 取消)")
            button.setStyleSheet("background: #5f8cff; color: #fff;")
        return start

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        if not self._capture_mode:
            super().keyPressEvent(event)
            return
        key = int(event.key())
        modifiers = int(event.modifiers())
        if key in (0x01000000,):  # Qt.Key_Escape
            self._cancel_capture()
            return
        # Build key sequence text
        parts: list[str] = []
        ctrl = bool(modifiers & 0x04000000)  # Qt.ControlModifier
        shift = bool(modifiers & 0x02000000)  # Qt.ShiftModifier
        alt = bool(modifiers & 0x08000000)  # Qt.AltModifier
        meta = bool(modifiers & 0x10000000)  # Qt.MetaModifier
        if ctrl:
            parts.append("Ctrl")
        if shift:
            parts.append("Shift")
        if alt:
            parts.append("Alt")
        if meta:
            parts.append("Meta")
        # Map common key codes
        key_map: dict[int, str] = {
            0x01000020: "Space", 0x01000021: "Delete", 0x01000022: "Backspace",
            0x01000023: "Tab", 0x01000024: "Return", 0x01000025: "Enter",
            0x01000030: "F1", 0x01000031: "F2", 0x01000032: "F3", 0x01000033: "F4",
            0x01000034: "F5", 0x01000035: "F6", 0x01000036: "F7", 0x01000037: "F8",
            0x01000038: "F9", 0x01000039: "F10", 0x0100003a: "F11", 0x0100003b: "F12",
            0x01000000: "Esc", 0x01000010: "Home", 0x01000011: "End",
            0x01000012: "Left", 0x01000013: "Up", 0x01000014: "Right", 0x01000015: "Down",
            0x01000016: "PageUp", 0x01000017: "PageDown",
            0x2b: "+", 0x2d: "-", 0x3d: "=",
        }
        key_text = key_map.get(key, chr(key) if 0x20 <= key < 0x100 else None)
        if key_text is None:
            return
        parts.append(key_text)
        seq = "+".join(parts)
        # Detect combo: if Ctrl+K was just pressed, allow a second key
        if len(self._capture_keys) == 0 and ctrl and not shift and not alt and key_text not in ("Ctrl", "Shift", "Alt", "Meta"):
            self._capture_keys.append(seq)
            if self._capture_button:
                self._capture_button.setText(f"组合键: {seq} + … (再按一键，Esc 取消)")
            return
        if self._capture_keys:
            self._capture_keys.append(seq)
            seq = " ".join(self._capture_keys)
        # Apply
        item = QTableWidgetItem(seq)
        row_idx = self._row_keys.index(self._capture_key) if self._capture_key in self._row_keys else -1
        if row_idx >= 0:
            self._table.setItem(row_idx, 1, item)
        self._finish_capture()

    def _cancel_capture(self) -> None:
        self._capture_mode = False
        self._capture_key = None
        self._capture_keys = []
        if self._capture_button:
            self._capture_button.setText("编辑")
            self._capture_button.setStyleSheet("")
            self._capture_button = None

    def _finish_capture(self) -> None:
        self._capture_mode = False
        self._capture_key = None
        self._capture_keys = []
        if self._capture_button:
            self._capture_button.setText("编辑")
            self._capture_button.setStyleSheet("")
            self._capture_button = None

    def _save_and_close(self) -> None:
        custom: dict[str, str] = {}
        for row in range(self._table.rowCount()):
            key = self._row_keys[row]
            label_item = self._table.item(row, 0)
            seq_item = self._table.item(row, 1)
            if not label_item or not seq_item:
                continue
            label = label_item.text()
            seq = seq_item.text().strip()
            default_info = SHORTCUT_DEFAULTS.get(key, ("", ""))
            default_seq = default_info[1] if default_info else ""
            if seq and seq != default_seq:
                custom[key] = seq
        save_custom_shortcuts(custom)
        if self._on_changed:
            self._on_changed(custom)
        self.close()
