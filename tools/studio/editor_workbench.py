#!/usr/bin/env python3
"""Workflow, page navigation, and canvas rendering mixin for Studio editor."""

from __future__ import annotations

import copy
import json
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPen
    from PyQt6.QtWidgets import QGraphicsLineItem, QListWidgetItem, QMessageBox
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import QPointF, Qt
    from PyQt5.QtGui import QColor, QPen
    from PyQt5.QtWidgets import QGraphicsLineItem, QListWidgetItem, QMessageBox
else:
    QPointF = Qt = QColor = QPen = QGraphicsLineItem = QListWidgetItem = QMessageBox = object

from codegen.graph import (
    EDGE_KIND_LABELS,
    NODE_CONTRACTS,
    PORT_DESCRIPTIONS,
    PORT_LABELS,
    PORT_RULES,
    callback_signature,
    edge_effect_description,
    node_generation_label,
)
from studio.core import page_for_node, page_hint, page_key, page_title, root_page, visible_nodes_for_page
from studio.editor_canvas import EdgeItem, GraphNodeItem
from studio.editor_registry import NODE_TEMPLATES, TYPE_LABELS


class WorkbenchMixin:
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
        aliases = {
            "代码": "代码补齐",
            "生成映射": "高级 · 生成映射",
            "文件树预览": "高级 · 文件树预览",
            "任务调度": "高级 · 任务调度",
            "Board Profile / Pin Planner": "高级 · Board Profile / Pin Planner",
            "Graph JSON": "高级 · Graph JSON",
        }
        expected = aliases.get(title, title)
        if expected.startswith("高级 ·") and hasattr(self, "_advanced_inspector_enabled") and not self._advanced_inspector_enabled:
            self.toggle_advanced_panels()
        for index in range(self.right_tabs.count()):
            current_title = self.right_tabs.tabText(index)
            if current_title == expected or current_title.replace("高级 · ", "") == title:
                self.right_tabs.setCurrentIndex(index)
                if hasattr(self, "inspector_nav"):
                    role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
                    for row in range(self.inspector_nav.count()):
                        item = self.inspector_nav.item(row)
                        if item and item.data(role) == index:
                            self.inspector_nav.setCurrentRow(row)
                            break
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
            "relations": "关系视图",
            "code": "关系视图",
            "release": "生成发布",
        }
        right_by_step = {
            "dashboard": "项目结构",
            "assembly": "属性表单",
            "relations": "属性表单",
            "code": "代码补齐",
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
            next_step = "先在“模块装配”里创建模块，再双击模块进入内部装配。"
        elif page.get("kind") == "module":
            next_step = "先添加输入设备和输出设备，再补处理逻辑，最后回到关系视图连线。"
        elif page.get("kind") == "state":
            next_step = "添加状态和转换，并在属性表单里补上 condition。"
        elif page.get("kind") == "comm":
            next_step = "添加发布者和订阅者，再到代码补齐页实现回调或 publish 逻辑。"
        else:
            next_step = "选择一个节点后先改属性，再到代码补齐和生成发布完成收尾。"
        self.workflow_hint.setText(f"当前页面：{page_title(page)}\n可见节点：{visible_count}\n当前选择：{selected}\n建议：{next_step}")
        if hasattr(self, "palette_label"):
            self.palette_label.setText(f"当前页面可添加：{page_title(page)}")

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
        next_steps = []
        if not modules:
            next_steps.append("1. 先到“模块装配”点击“新增模块”。")
        elif len([node for node in nodes if node.get("type") != "project.module"]) == 0:
            next_steps.append("1. 进入模块后，从左侧模板库添加输入设备、输出设备或处理逻辑。")
        else:
            next_steps.append("1. 到“关系视图”确认输入、处理、输出之间的连接关系。")
        if missing:
            next_steps.append("2. 到“代码补齐”页点击“一键生成缺失回调”，再补业务逻辑。")
        if errors or warnings:
            next_steps.append("3. 到“实时校验”先处理红色错误，再看黄色警告。")
        else:
            next_steps.append("3. 当前已经基本就绪，可以到“生成发布”生成 application。")
        lines = [
            f"项目：{project.get('name', 'unnamed')}",
            f"tick：{project.get('tick_ms', 1)} ms",
            f"Board Profile：{board.get('profile', project.get('board_profile', 'generic-mock'))}",
            "",
            "你现在在哪一步",
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
            "下一步建议",
        ]
        lines.extend(next_steps)
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
        lines = ["生成发布检查清单", "", "先让下面五项尽量都变成 [OK]，再点击生成 application。", ""]
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
                line = EdgeItem(edge, self)
                line.setLine(a.x(), a.y(), b.x(), b.y())
                line.setPen(self.edge_pen_for_item(edge, selected=str(edge.get("id")) == getattr(self, "selected_edge_id", None)))
                kind_label = EDGE_KIND_LABELS.get(str(edge.get("kind", "generic")), str(edge.get("kind", "generic")))
                effect = ""
                src_node = self._find_node(src)
                dst_node = self._find_node(dst)
                if src_node and dst_node:
                    effect = "\n生成/语义：" + edge_effect_description(src_node, dst_node, edge.get("from_port"), edge.get("to_port"))
                tooltip = f"{kind_label}: {src}.{edge.get('from_port', 'out')} → {dst}.{edge.get('to_port', 'in')}{effect}"
                line.setToolTip(tooltip)
                line.setZValue(-1)
                self.scene.addItem(line)
                self.edge_items.append(line)

    def refresh_json_editor(self) -> None:
        self.graph_json_editor.setPlainText(json.dumps(self.graph, ensure_ascii=False, indent=2))
        self.schedule_autosave()

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
        if node_id is not None:
            self.selected_edge_id = None
            for item in self.edge_items:
                item.setPen(self.edge_pen_for_item(item.edge, selected=False))
        self.current_node_id = node_id
        node = self._find_node(node_id) if node_id else None
        if not node and node_id is None:
            node = self.page_source_node()
            if node:
                self.current_node_id = node.get("id")
        if not node:
            if node_id is not None:
                self.current_node_id = None
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
                template.setdefault("parent", owner_id)
            elif node_type != "custom.card":
                template.setdefault("module", owner_id)
            else:
                template.setdefault("scope", f"module:{owner_id}")
                template.setdefault("module", owner_id)
            return True
        if kind == "state":
            allowed = {"state.state", "state.transition"}
            if node_type not in allowed:
                QMessageBox.warning(self, "页面类型不匹配", "状态机页面只允许添加 State / Transition；说明卡片请放在模块或根页面。")
                return False
            template.setdefault("machine", owner_id)
            return True
        if kind == "comm":
            allowed = {"event.publisher", "event.subscriber", "custom.card"}
            if node_type not in allowed:
                QMessageBox.warning(self, "页面类型不匹配", "通信页面只建议添加 Publisher / Subscriber / 说明卡片。")
                return False
            if node_type != "custom.card":
                template.setdefault("topic", owner_id)
            else:
                template.setdefault("scope", f"comm:{owner_id}")
            return True
        return True

    def filter_palette(self, text: str) -> None:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        cat_role = role + 1
        lowered = text.strip().lower()
        categories_with_visible: set[str] = set()
        collapsed_categories: set[str] = {cat for cat, collapsed in self._palette_category_visibility.items() if collapsed}
        for row in range(self.palette.count()):
            item = self.palette.item(row)
            node_type = item.data(role)
            if node_type == "__category__":
                continue
            label = item.text().lower()
            cat = item.data(cat_role)
            cat_str = str(cat) if cat else ""
            if lowered:
                visible = lowered in label or lowered in (node_type or "")
            else:
                visible = cat_str not in collapsed_categories
            item.setHidden(not visible)
            if visible and cat:
                categories_with_visible.add(str(cat))
        for row in range(self.palette.count()):
            item = self.palette.item(row)
            if item.data(role) == "__category__":
                cat_name = item.data(cat_role)
                cat_str = str(cat_name)
                collapsed = cat_str in collapsed_categories
                has_visible_children = cat_str in categories_with_visible
                if lowered:
                    item.setHidden(not has_visible_children)
                    if has_visible_children:
                        item.setText(f"▾ {cat_name}")
                else:
                    item.setHidden(False)
                    arrow = "▸" if collapsed else "▾"
                    item.setText(f"{arrow} {cat_name}")

    def _on_palette_double_click(self, item: QListWidgetItem) -> None:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        cat_role = role + 1
        node_type = item.data(role)
        if node_type == "__category__":
            cat_name = str(item.data(cat_role))
            collapsed = self._palette_category_visibility.get(cat_name, False)
            self._palette_category_visibility[cat_name] = not collapsed
            self.filter_palette(self.palette_search.text())
            return
        self.add_selected_card()

    def add_selected_card(self) -> None:
        item = self.palette.currentItem()
        if not item:
            QMessageBox.information(self, "未选择模板", "请先在左侧「快速添加」面板中点击选择一个模板卡片，然后按 Ctrl+M 或点击「添加到当前页面」按钮。")
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        node_type = item.data(role)
        if node_type == "__category__":
            QMessageBox.information(self, "选择了分类标题", "当前选中了分类标题「{0}」，请双击展开分类后选择一个具体模板。".format(item.text().lstrip("▾▸ ")))
            return
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
