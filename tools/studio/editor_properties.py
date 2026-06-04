#!/usr/bin/env python3
"""Property inspector and pin planner mixin for the Studio editor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QMessageBox, QPushButton, QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget, QLabel, QHBoxLayout
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor
    from PyQt5.QtWidgets import QCheckBox, QComboBox, QMessageBox, QPushButton, QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget, QLabel, QHBoxLayout
else:
    Qt = QBrush = QColor = QCheckBox = QComboBox = QMessageBox = QPushButton = QPlainTextEdit = QTableWidgetItem = QVBoxLayout = QWidget = QLabel = QHBoxLayout = object

from codegen import c_ident
from codegen.graph import NODE_CONTRACTS, callback_signature
from studio.core import apply_board_profile_defaults_to_graph, property_choices as core_property_choices
from studio.editor_canvas import form_value_text, parse_form_value
from studio.editor_registry import NODE_TEMPLATES, PROPERTY_FIELD_ORDER, TYPE_LABELS
from studio.model import BOARD_PROFILES, GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS


class PropertyMixin:
    PROPERTY_SECTIONS = ("basic", "parameters", "contracts", "advanced")

    def property_choices(self, node: dict[str, Any], key: str) -> list[str]:
        return core_property_choices(self.graph, node, key, NODE_TEMPLATES)

    def property_tables(self) -> list[Any]:
        if hasattr(self, "property_tables_by_section"):
            return [table for table in self.property_tables_by_section.values() if table is not None]
        return [self.property_table] if hasattr(self, "property_table") else []

    def clear_property_tables(self) -> None:
        for table in self.property_tables():
            table.setRowCount(0)

    def property_section(self, node: dict[str, Any], key: str, role: str) -> str:
        if key in {"display_name", "id", "type", "description"}:
            return "basic"
        if role == "数据契约" or key in {"input_contract", "output_contract", "input_type", "output_type", "payload_type", "data_type", "output_desc", "input_size", "output_size", "input_align", "output_align", "size_expr", "data_expr"}:
            return "contracts"
        if key in {"priority", "timeout_ms", "interval_ms", "ctx", "ctx_name", "bus_id", "topic_id", "max_iterations", "anti_windup", "binary_mode", "enabled", "user"}:
            return "advanced"
        return "parameters"

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
        if key in {"display_name", "description"}:
            return "显示"
        if key == "name":
            return "兼容"
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
        self.clear_property_tables()
        node_type = str(node.get("type", ""))
        ordered_keys = ["display_name", "id", "type", "description"]
        ordered_keys.extend(key for key in PROPERTY_FIELD_ORDER.get(str(node.get("type")), []) if key not in ordered_keys)
        ordered_keys.extend(key for key in node if key not in ordered_keys)
        for key in ordered_keys:
            if key == "name" and not self._uses_legacy_name_field(node_type):
                continue
            value = node.get(key, "")
            choices = self.property_choices(node, str(key))
            kind = self.property_widget_kind(node, str(key), value, choices)
            issue = self.property_issue(node, str(key), value, choices)
            role = self.property_contract_role(node, str(key))
            section = self.property_section(node, str(key), role)
            table = getattr(self, "property_tables_by_section", {}).get(section, self.property_table)
            row = table.rowCount()
            table.insertRow(row)
            key_item = QTableWidgetItem(str(key))
            if issue:
                key_item.setBackground(QBrush(QColor("#5b1f24")))
                key_item.setForeground(QBrush(QColor("#ffb3b3")))
                key_item.setToolTip(issue)
            table.setItem(row, 0, key_item)
            if choices:
                combo = QComboBox()
                combo.addItems([str(item) for item in choices])
                if str(value) not in [str(item) for item in choices]:
                    combo.addItem(str(value))
                combo.setCurrentText(str(value))
                if issue:
                    combo.setToolTip(issue)
                table.setCellWidget(row, 1, combo)
            elif kind == "布尔开关":
                check = QCheckBox()
                check.setChecked(bool(value) if not isinstance(value, str) else value.lower() in {"1", "true", "yes", "on"})
                if issue:
                    check.setToolTip(issue)
                table.setCellWidget(row, 1, check)
            else:
                item = QTableWidgetItem(form_value_text(value))
                if key == "id":
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable if hasattr(Qt, "ItemFlag") else item.flags())
                    item.setToolTip("id 由 display_name 自动生成，仅用于查看。")
                if issue:
                    item.setBackground(QBrush(QColor("#5b1f24")))
                    item.setForeground(QBrush(QColor("#ffb3b3")))
                    item.setToolTip(issue)
                    if node.get("type") == "state.transition" and key == "condition" and not str(value).strip():
                        item.setText("<必填：条件函数名>")
                table.setItem(row, 1, item)
            type_item = QTableWidgetItem(kind)
            if issue:
                type_item.setBackground(QBrush(QColor("#5b1f24")))
                type_item.setForeground(QBrush(QColor("#ffb3b3")))
                type_item.setToolTip(issue)
            table.setItem(row, 2, type_item)
            role_item = QTableWidgetItem(role)
            role_item.setToolTip(self.property_role_tooltip(node, str(key), role))
            if role in {"必填", "至少一项", "回调"}:
                role_item.setForeground(QBrush(QColor("#ffecb3")))
            elif role == "引用":
                role_item.setForeground(QBrush(QColor("#b3e5fc")))
            elif role in {"显示", "主键", "数据契约"}:
                role_item.setForeground(QBrush(QColor("#c7d4e8")))
            table.setItem(row, 3, role_item)

    def property_role_tooltip(self, node: dict[str, Any], key: str, role: str) -> str:
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        callbacks = contract.get("callbacks", {})
        if key in callbacks:
            return f"用户代码需要实现该回调，签名：{callback_signature(callbacks[key])}"
        if key == "id":
            return "卡片主键。用于连线、页面、归属和 codegen 引用；创建时自动分配，修改时必须保持唯一。"
        if key == "event_trigger":
            return "状态机事件触发器。必须写成 topic:<event.topic节点id> 或 event:<事件名>。topic: 前缀表示按 topic_id/payload 触发；event: 前缀表示按自定义事件名触发。"
        if key == "interval_ms":
            return "自动发布最小间隔（毫秒）。0 表示不额外节流；如果 payload 没变化，系统仍会自动跳过重复发布。"
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
        old_call = str(old_node.get("call", "app_custom_task_10ms"))
        old_display_name = str(old_node.get("display_name", old_node.get("id", "custom_task_10ms")))
        old_token = f"{old_period}ms"
        new_token = f"{new_period}ms"
        if old_token in old_call:
            updated["call"] = old_call.replace(old_token, new_token)
        if old_token in old_display_name:
            updated["display_name"] = old_display_name.replace(old_token, new_token)

    def apply_property_form(self) -> None:
        if not self.current_node_id:
            return
        node = self._find_node(self.current_node_id)
        if not node:
            return
        old_id = str(node.get("id", self.current_node_id))
        updated: dict[str, Any] = {}
        for table in self.property_tables():
            for row in range(table.rowCount()):
                key_item = table.item(row, 0)
                value_item = table.item(row, 1)
                value_widget = table.cellWidget(row, 1)
                if not key_item:
                    continue
                key = key_item.text().strip()
                if not key:
                    continue
                if isinstance(value_widget, QComboBox):
                    value = parse_form_value(value_widget.currentText())
                elif isinstance(value_widget, QCheckBox):
                    value = value_widget.isChecked()
                else:
                    raw_value = value_item.text() if value_item else ""
                    if raw_value == "<必填：条件函数名>":
                        raw_value = ""
                    value = parse_form_value(raw_value)
                updated[key] = value
        updated["id"] = old_id
        new_id = old_id
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
                    raise ValueError(f'"{key}" 的值必须是对象')
                if "ports" not in profile:
                    raise ValueError(f'"{key}" 缺少 ports 字段')
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

    def _add_pin_row(self, row_owner: str, usage: str, port: Any, pin: Any, note: str) -> None:
        row = self.pin_table.rowCount()
        self.pin_table.insertRow(row)
        self.pin_table.setItem(row, 0, QTableWidgetItem(str(row_owner)))
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
