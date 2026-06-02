#!/usr/bin/env python3
"""Code and JSON editor mixin for the Studio editor."""

from __future__ import annotations

import copy
import json
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtWidgets import QInputDialog, QMessageBox
else:
    QInputDialog = QMessageBox = object

from studio.editor_registry import NODE_TEMPLATES


class CodeEditorMixin:
    def select_code_file(self, row: int) -> None:
        if getattr(self, "_reverting_code_selection", False):
            return
        previous = self.current_code_index
        if previous is not None and row != previous and self.code_buffer_is_dirty():
            answer = QMessageBox.question(
                self,
                "代码未保存",
                "当前代码缓冲区有未保存更改。切换文件前是否先保存到 Graph.custom_files？",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                self._reverting_code_selection = True
                self.code_files.setCurrentRow(previous)
                self._reverting_code_selection = False
                return
            if answer == QMessageBox.StandardButton.Save:
                self.apply_code_file(record_history=True)
        self.current_code_index = row if row >= 0 else None
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index is None or self.current_code_index >= len(files):
            self._suppress_code_text_events = True
            self.code_editor.clear()
            self._suppress_code_text_events = False
            self._set_loaded_code_content("")
            if hasattr(self, "code_status_label"):
                self.code_status_label.setText("未选择文件")
            return
        item = files[self.current_code_index]
        content = item.get("content", "")
        self._suppress_code_text_events = True
        self.code_editor.setPlainText(content)
        self._suppress_code_text_events = False
        self._set_loaded_code_content(content)
        if hasattr(self, "code_status_label"):
            self.code_status_label.setText(f"{item.get('path', 'unnamed')} · {content.count(chr(10)) + 1} 行")

    def add_code_file(self) -> None:
        path, ok = QInputDialog.getText(self, "Add custom code", "Relative file path (for example app_custom.c):")
        if not ok or not path:
            return
        self.push_undo()
        self.graph.setdefault("custom_files", []).append({"path": path, "content": self.DEFAULT_CUSTOM_C if path.endswith(".c") else ""})
        self.current_code_index = len(self.graph["custom_files"]) - 1
        self.refresh_code_list()
        self.refresh_json_editor()

    def apply_code_file(self, record_history: bool = True) -> None:
        if self.current_code_index is None:
            return
        files = self.graph.setdefault("custom_files", [])
        if self.current_code_index >= len(files):
            return
        next_content = self.code_editor.toPlainText()
        if files[self.current_code_index].get("content") == next_content:
            return
        if record_history:
            self.push_undo()
        else:
            self._mark_dirty()
        files[self.current_code_index]["content"] = next_content
        self._set_loaded_code_content(next_content)
        if hasattr(self, "code_status_label"):
            self.code_status_label.setText(f"{files[self.current_code_index].get('path', 'unnamed')} · 已保存")
        self.refresh_json_editor()

    def format_code_file(self) -> None:
        text = self.code_editor.toPlainText()
        formatted = self.format_c_like_code(text)
        if formatted != text:
            self.code_editor.setPlainText(formatted)

    def format_c_like_code(self, text: str) -> str:
        protected: list[str] = []

        def protect(match: Any) -> str:
            protected.append(match.group(0))
            return f"__PROTECTED_{len(protected) - 1}__"

        import re

        text = text.replace("\r\n", "\n").replace("\t", "  ")
        text = re.sub(r"/\*.*?\*/", protect, text, flags=re.S)
        text = re.sub(r"//[^\n]*", protect, text)
        text = re.sub(r'"(?:[^"\\]|\\.)*"', protect, text)
        text = re.sub(r"'(?:[^'\\]|\\.)'", protect, text)
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
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Graph JSON 无效", str(exc))

    def project_wizard(self) -> None:
        templates = {
            "通用嵌入式应用": self.default_graph,
            "空白画布（从零开始）": lambda: {"project": {"name": "blank_project", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": '#include "efw/efw.h"\n'}], "ui": {"positions": {}}},
            "空白多模块项目": lambda: {"project": {"name": "new_modular_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": '#include "efw/efw.h"\n'}], "ui": {"positions": {"control_module": [40, 40]}}},
            "状态机项目": lambda: {"project": {"name": "state_machine_app", "tick_ms": 1}, "board": {"profile": "generic-mock", "pin_plan": []}, "nodes": [copy.deepcopy(NODE_TEMPLATES["project.module"]), copy.deepcopy(NODE_TEMPLATES["state.machine"]), copy.deepcopy(NODE_TEMPLATES["state.state"]), copy.deepcopy(NODE_TEMPLATES["state.transition"])], "edges": [], "flows": [], "tasks": [], "custom_files": [{"path": "app_custom.c", "content": '#include "efw/efw.h"\n'}], "ui": {"positions": {}}},
        }
        choice, ok = QInputDialog.getItem(self, "项目向导", "选择模板", list(templates), 0, False)
        if not ok or not choice:
            return
        if not self._confirm_discard_changes():
            return
        self._reset_autosave_session()
        self.graph_path = None
        self.push_undo()
        self.graph = templates[choice]()
        self.current_node_id = None
        self._is_dirty = False
        self.refresh_all()

    def validate_current_graph(self) -> bool:
        return self.refresh_validation_panel(show_dialog=True)
