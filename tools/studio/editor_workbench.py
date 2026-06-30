#!/usr/bin/env python3
"""Workflow, page navigation, and canvas rendering mixin for Studio editor."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import importlib.util

from studio.qt_compat import (
    QPointF, QRectF, Qt,
    QColor, QPen,
    QGraphicsLineItem, QListWidgetItem, QMessageBox, QInputDialog,
)

from codegen.graph import (
    EDGE_KIND_LABELS,
    NODE_CONTRACTS,
    PORT_DESCRIPTIONS,
    PORT_LABELS,
    PORT_RULES,
    callback_signature,
    can_connect_ports,
    edge_effect_description,
    node_generation_label,
)
from codegen import c_ident
from pypinyin import lazy_pinyin
from studio.core import page_for_node, page_hint, page_key, page_title, root_page, visible_nodes_for_page
from studio.editor_canvas import BackdropItem, EdgeItem, GraphNodeItem
from studio.editor_registry import NODE_TEMPLATES, TYPE_LABELS, display_label


OUTPUT_PORT_DEPENDENCIES: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "sensor.line_tracking": {
        "out": {"sensor": ("hal",), "event_source": ("hal",)},
    },
    "sensor.custom": {
        "out": {"sensor": ("hal",), "event_source": ("hal",)},
    },
    "event.publisher": {
        "out": {"event": ("topic", "event_source")},
    },
    "event.subscriber": {
        "out": {"event": ("topic",)},
    },
    "processor.custom": {
        "out": {
            "processor": ("sensor", "module_input"),
            "algorithm": ("algorithm", "sensor"),
            "control": ("algorithm",),
            "module_output": ("module_input",),
            "event_source": ("event",),
        },
    },
    "algorithm.pid": {
        "out": {"algorithm": ("sensor", "processor")},
    },
    "algorithm.custom": {
        "out": {"algorithm": ("sensor", "processor")},
    },
    "module.custom": {
        "out": {
            "module": ("schedule",),
            "module_output": ("module_input",),
            "event_source": ("event",),
        },
    },
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


class WorkbenchMixin:
    def _uses_legacy_name_field(self, node_type: str | None) -> bool:
        return str(node_type) in {"data.enum", "data.struct"}

    def _default_display_name(self, template: dict[str, Any], node_type: str) -> str:
        if str(template.get("display_name", "")).strip():
            return str(template.get("display_name")).strip()
        if self._uses_legacy_name_field(node_type) and str(template.get("name", "")).strip():
            return str(template.get("name")).strip()
        return str(template.get("id") or display_label(node_type) or node_type)

    def _transliterate_name_token(self, text: str, fallback: str = "name") -> str:
        raw = str(text or "").strip()
        if not raw:
            return fallback
        ascii_text = re.sub(r"[^0-9A-Za-z_]+", "_", raw)
        ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")
        if ascii_text:
            return c_ident(ascii_text, fallback=fallback)
        pinyin_text = "_".join(part for part in lazy_pinyin(raw) if part)
        token = c_ident(pinyin_text, fallback="")
        if token:
            return token
        encoded_parts: list[str] = []
        for ch in raw:
            if re.match(r"[0-9A-Za-z]", ch):
                encoded_parts.append(ch.lower())
            elif ch in {" ", "-", "/", "_"}:
                encoded_parts.append("_")
            else:
                encoded_parts.append(f"u{ord(ch):x}")
        return c_ident("_".join(encoded_parts), fallback=fallback)

    def _node_type_token(self, node_type: str) -> str:
        parts = [part for part in str(node_type).split(".") if part]
        if len(parts) >= 2:
            return c_ident(f"{parts[0]}_{parts[-1]}", fallback="node")
        return c_ident(parts[-1] if parts else "node", fallback="node")

    def _module_scope_token(self, template: dict[str, Any], node_type: str) -> str:
        module_chain: list[str] = []
        if node_type == "project.module":
            current_id = str(template.get("id") or "").strip()
            current_parent = str(template.get("parent") or "").strip()
        else:
            current_id = str(template.get("module") or "").strip()
            current_parent = ""
        while current_id:
            module_chain.append(c_ident(current_id, fallback="module"))
            module_node = self._find_node(current_id) if hasattr(self, "_find_node") else None
            if module_node is None and node_type == "project.module" and current_id == str(template.get("id") or ""):
                current_parent = str(template.get("parent") or "").strip()
            else:
                current_parent = str(module_node.get("parent") or "").strip() if isinstance(module_node, dict) else ""
            current_id = current_parent
        if module_chain:
            return "__".join(reversed(module_chain))
        page = self.active_page() if hasattr(self, "active_page") else {"kind": "root", "id": ""}
        if page.get("kind") == "module" and page.get("id"):
            return c_ident(str(page.get("id")), fallback="root")
        return "root"

    def _prompt_display_name(self, node_type: str, initial_text: str) -> str | None:
        label = display_label(node_type)
        text, ok = QInputDialog.getText(self, "添加卡片", f"请输入“{label}”的显示名称", text=initial_text)
        if not ok:
            return None
        display_name = str(text).strip()
        if not display_name:
            QMessageBox.warning(self, "缺少显示名称", "display_name 不能为空；已取消添加卡片。")
            return None
        return display_name

    def _derive_node_id(self, display_name: str, fallback_id: str, existing_ids: set[str], node_type: str, template: dict[str, Any]) -> str:
        module_token = self._module_scope_token(template, node_type)
        type_token = self._node_type_token(node_type)
        name_token = self._transliterate_name_token(display_name, fallback="name")
        base_id = c_ident(f"{module_token}__{type_token}__{name_token}", fallback=fallback_id)
        new_id = base_id
        suffix = 1
        while new_id in existing_ids:
            suffix += 1
            new_id = f"{base_id}_{suffix}"
        return new_id

    def _normalize_display_fields(self, node: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        node_type = str(node.get("type", ""))
        if self._uses_legacy_name_field(node_type):
            return
        display_name = str(node.get("display_name", "")).strip()
        legacy_name = str(node.get("name", "")).strip()
        if not display_name and legacy_name:
            node["display_name"] = legacy_name
        node.pop("name", None)

    def _scene_item_alive(self, item: Any) -> bool:
        if item is None:
            return False
        try:
            return item.scene() is not None
        except RuntimeError:
            return False

    def _safe_scene_call(self, item: Any, method_name: str, *args: Any, **kwargs: Any) -> bool:
        if not self._scene_item_alive(item):
            return False
        try:
            getattr(item, method_name)(*args, **kwargs)
            return True
        except RuntimeError:
            return False

    def _iter_live_node_items(self) -> list[tuple[str, Any]]:
        live_items: list[tuple[str, Any]] = []
        stale_node_ids: list[str] = []
        for node_id, item in list(self.node_items.items()):
            if self._scene_item_alive(item):
                live_items.append((node_id, item))
            else:
                stale_node_ids.append(node_id)
        for node_id in stale_node_ids:
            self.node_items.pop(node_id, None)
        return live_items

    def _iter_live_edge_items(self) -> list[Any]:
        live_edges = [edge_item for edge_item in list(getattr(self, "edge_items", [])) if self._scene_item_alive(edge_item)]
        self.edge_items = live_edges
        return live_edges

    def _iter_live_ports(self, item: Any) -> list[Any]:
        ports = []
        for port in getattr(item, "ports", []):
            if self._scene_item_alive(port):
                ports.append(port)
        return ports

    def _iter_live_backdrop_items(self) -> list[Any]:
        backdrops = []
        for item in self.scene.items():
            if isinstance(item, BackdropItem) and self._scene_item_alive(item):
                backdrops.append(item)
        return backdrops

    def _set_backdrop_opacity(self, selected_ids: set[str] | None = None, active_backdrop_ids: set[str] | None = None, default_opacity: float = 0.95, dim_opacity: float = 0.18) -> None:
        if active_backdrop_ids is None:
            active_backdrop_ids = set()
        for item in self._iter_live_backdrop_items():
            item_id = str(item.group.get("id", ""))
            if selected_ids is None:
                opacity = default_opacity
            else:
                opacity = default_opacity if item_id in active_backdrop_ids else dim_opacity
            self._safe_scene_call(item, "setOpacity", opacity)

    def _apply_visual_state(self, node_opacity_by_id: dict[str, float] | None = None, edge_opacity_by_key: dict[tuple[str, str], float] | None = None, active_backdrop_ids: set[str] | None = None, default_node_opacity: float = 1.0, default_edge_opacity: float = 1.0, default_backdrop_opacity: float = 0.95, dim_backdrop_opacity: float = 0.18) -> None:
        if node_opacity_by_id is None:
            node_opacity_by_id = {}
        if edge_opacity_by_key is None:
            edge_opacity_by_key = {}
        if active_backdrop_ids is None:
            active_backdrop_ids = set()

        for item_id, item in self._iter_live_node_items():
            self._safe_scene_call(item, "setOpacity", node_opacity_by_id.get(item_id, default_node_opacity))
        for edge_item in self._iter_live_edge_items():
            src = str(edge_item.edge.get("from", ""))
            dst = str(edge_item.edge.get("to", ""))
            self._safe_scene_call(edge_item, "setOpacity", edge_opacity_by_key.get((src, dst), default_edge_opacity))
        if active_backdrop_ids:
            self._set_backdrop_opacity(active_backdrop_ids=active_backdrop_ids, default_opacity=default_backdrop_opacity, dim_opacity=dim_backdrop_opacity)
        else:
            self._set_backdrop_opacity(default_opacity=default_backdrop_opacity, dim_opacity=dim_backdrop_opacity)

    def _prune_stale_scene_items(self) -> None:
        self._iter_live_node_items()
        self._iter_live_edge_items()

    def normalize_graph_runtime_state(self) -> None:
        nodes = [node for node in self.graph.get("nodes", []) if isinstance(node, dict)]
        for node in nodes:
            self._normalize_display_fields(node)
        node_ids = {str(node.get("id", "")) for node in nodes if node.get("id")}
        self.graph["nodes"] = nodes
        self.graph["edges"] = [
            edge
            for edge in self.graph.get("edges", [])
            if isinstance(edge, dict)
            and str(edge.get("from", "")) in node_ids
            and str(edge.get("to", "")) in node_ids
        ]

    def refresh_all(self) -> None:
        self.normalize_graph_runtime_state()
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
        self.update_canvas_lod(getattr(self.view, "zoom_level", 1.0) if hasattr(self, "view") else 1.0)

    def set_right_tab(self, title: str) -> None:
        if title in {"实时校验", "任务调度"} and hasattr(self, "bottom_tabs"):
            for index in range(self.bottom_tabs.count()):
                if self.bottom_tabs.tabText(index) == title:
                    if hasattr(self, "bottom_dock"):
                        self.bottom_dock.show()
                    self.bottom_tabs.setCurrentIndex(index)
                    return
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
        tabs = getattr(self, "center_tabs", None) or getattr(self, "workspace_tabs", None)
        if tabs is None:
            return
        aliases = {
            "项目总览": "🏠 项目总览",
            "模块装配": "📦 模块装配",
            "关系视图": "🔵 关系视图",
            "生成发布": "🚀 生成发布",
        }
        expected = aliases.get(title, title)
        for index in range(tabs.count()):
            current_title = tabs.tabText(index)
            if current_title == expected or current_title.replace("🏠 ", "").replace("📦 ", "").replace("🔵 ", "").replace("🚀 ", "") == title:
                tabs.setCurrentIndex(index)
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
        runtime_summary = self.runtime_summary() if hasattr(self, "runtime_summary") else {}
        publisher_count = len(runtime_summary.get("publishers", [])) if isinstance(runtime_summary, dict) else 0
        state_machine_count = len(runtime_summary.get("state_machines", [])) if isinstance(runtime_summary, dict) else 0
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
        self.workflow_hint.setText(f"当前页面：{page_title(page)}\n可见节点：{visible_count}\n当前选择：{selected}\n运行时发布者：{publisher_count}\n运行时状态机：{state_machine_count}\n建议：{next_step}")
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
        runtime_summary = self.runtime_summary() if hasattr(self, "runtime_summary") else {}
        publishers = runtime_summary.get("publishers", []) if isinstance(runtime_summary, dict) else []
        machines = runtime_summary.get("state_machines", []) if isinstance(runtime_summary, dict) else []
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
            f"- 发布者：{len(publishers)}",
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
        runtime_summary = self.runtime_summary() if hasattr(self, "runtime_summary") else {}
        publishers = runtime_summary.get("publishers", []) if isinstance(runtime_summary, dict) else []
        state_machines = runtime_summary.get("state_machines", []) if isinstance(runtime_summary, dict) else []
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
        if publishers or state_machines:
            lines.append("")
            lines.append("运行时摘要：")
            lines.append(f"- 自动/手动发布者：{len(publishers)}")
            lines.append(f"- 状态机：{len(state_machines)}")
            for item in publishers[:8]:
                lines.append(f"  - publisher {item.get('id')} | mode={item.get('mode')} | stage={item.get('stage')}")
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
        module = copy.deepcopy(NODE_TEMPLATES["project.module"])
        self._normalize_display_fields(module)
        display_name = self._prompt_display_name("project.module", self._default_display_name(module, "project.module"))
        if display_name is None:
            return
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        module["display_name"] = display_name
        module["id"] = self._derive_node_id(display_name, str(module.get("id", "module")), existing, "project.module", module)
        self.push_undo()
        self.graph.setdefault("nodes", []).append(module)
        self.current_node_id = str(module["id"])
        self.refresh_all()
        self.open_node_location(str(module["id"]))

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
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        positions = self.page_positions()
        visible_nodes = self.visible_nodes()
        for group in self.graph.get("ui", {}).get("backdrops", []):
            if not isinstance(group, dict):
                continue
            backdrop = BackdropItem(group, self)
            backdrop.update_geometry()
            self.scene.addItem(backdrop)
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
        self.apply_focus_mode(self.focus_node_id)

    def update_canvas_lod(self, zoom_level: float) -> None:
        lod = max(0.2, min(2.0, zoom_level))
        for item in self.node_items.values():
            item.update_lod(lod)

    def related_focus_ids(self, node_id: str) -> set[str]:
        related = {node_id}
        changed = True
        while changed:
            changed = False
            for edge in self.graph.get("edges", []):
                src = str(edge.get("from", ""))
                dst = str(edge.get("to", ""))
                if src in related and dst and dst not in related:
                    related.add(dst)
                    changed = True
                if dst in related and src and src not in related:
                    related.add(src)
                    changed = True
        return related

    def apply_focus_mode(self, node_id: str | None) -> None:
        self._prune_stale_scene_items()
        if not node_id:
            self._apply_visual_state()
            return
        focus_ids = self.related_focus_ids(node_id)
        active_backdrops = {
            str(group.get("id"))
            for group in self.graph.get("ui", {}).get("backdrops", [])
            if any(str(item_id) in focus_ids for item_id in group.get("node_ids", []))
        }
        self._apply_visual_state(
            node_opacity_by_id={item_id: (1.0 if item_id in focus_ids else 0.22) for item_id, _ in self._iter_live_node_items()},
            edge_opacity_by_key={
                (str(edge_item.edge.get("from", "")), str(edge_item.edge.get("to", ""))): (
                    1.0 if str(edge_item.edge.get("from", "")) in focus_ids and str(edge_item.edge.get("to", "")) in focus_ids else 0.18
                )
                for edge_item in self._iter_live_edge_items()
            },
            active_backdrop_ids=active_backdrops,
            default_backdrop_opacity=0.96,
        )

    def apply_selected_nodes_focus(self, focus_ids: set[str]) -> None:
        self._prune_stale_scene_items()
        if not focus_ids:
            self.apply_focus_mode(None)
            return
        active_backdrops = {
            str(group.get("id"))
            for group in self.graph.get("ui", {}).get("backdrops", [])
            if any(str(item_id) in focus_ids for item_id in group.get("node_ids", []))
        }
        self._apply_visual_state(
            node_opacity_by_id={item_id: (1.0 if item_id in focus_ids else 0.22) for item_id, _ in self._iter_live_node_items()},
            edge_opacity_by_key={
                (str(edge_item.edge.get("from", "")), str(edge_item.edge.get("to", ""))): (
                    1.0 if str(edge_item.edge.get("from", "")) in focus_ids and str(edge_item.edge.get("to", "")) in focus_ids else 0.18
                )
                for edge_item in self._iter_live_edge_items()
            },
            active_backdrop_ids=active_backdrops,
            default_backdrop_opacity=0.96,
        )

    def handle_scene_selection_changed(self) -> None:
        self._prune_stale_scene_items()
        selected_ids: list[str] = []
        for node_id, item in self._iter_live_node_items():
            try:
                if item.isSelected():
                    selected_ids.append(node_id)
            except RuntimeError:
                continue
        if len(selected_ids) > 1:
            self.selected_edge_id = None
            self.current_node_id = selected_ids[0]
            self.focus_node_id = selected_ids[0]
            self.apply_selected_nodes_focus(set(selected_ids))
            if hasattr(self, "selected_label"):
                self.selected_label.setText(f"已选择 {len(selected_ids)} 个卡片")
            if hasattr(self, "ports_label"):
                self.ports_label.setText("端口：多选模式")
            return
        if len(selected_ids) == 1:
            self.select_node(selected_ids[0])
            return
        if not self.selected_edge_id:
            self.current_node_id = None
            self.focus_node_id = None
            self.apply_focus_mode(None)

    def select_backdrop(self, group: dict[str, Any] | None) -> None:
        self._prune_stale_scene_items()
        if not group:
            self.focus_node_id = None
            self.apply_focus_mode(None)
            return
        node_ids = [str(node_id) for node_id in group.get("node_ids", [])]
        self.focus_node_id = node_ids[0] if node_ids else None
        if not node_ids:
            self.apply_focus_mode(None)
            return
        focus_ids = set(node_ids)
        self._apply_visual_state(
            node_opacity_by_id={item_id: (1.0 if item_id in focus_ids else 0.22) for item_id, _ in self._iter_live_node_items()},
            edge_opacity_by_key={
                (str(edge_item.edge.get("from", "")), str(edge_item.edge.get("to", ""))): (
                    1.0 if str(edge_item.edge.get("from", "")) in focus_ids and str(edge_item.edge.get("to", "")) in focus_ids else 0.18
                )
                for edge_item in self._iter_live_edge_items()
            },
            active_backdrop_ids={str(group.get("id", ""))},
            default_backdrop_opacity=0.96,
        )

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

    def compatible_target_ids(self, start_port) -> set[str]:
        if not self._scene_item_alive(start_port):
            return set()
        compatible: set[str] = set()
        for node_id, item in self._iter_live_node_items():
            for port in self._iter_live_ports(item):
                if start_port.direction == port.direction:
                    continue
                out_port = start_port if start_port.direction == "out" else port
                in_port = port if port.direction == "in" else start_port
                if can_connect_ports(out_port.node_item.node, in_port.node_item.node, out_port.port_type, in_port.port_type):
                    compatible.add(node_id)
                    break
        return compatible

    def show_compatible_target_preview(self, start_port) -> None:
        self._prune_stale_scene_items()
        if not self._scene_item_alive(start_port):
            return
        source_id = str(start_port.node_item.node.get("id"))
        for node_id, item in self._iter_live_node_items():
            node = item.node
            self._safe_scene_call(item, "setOpacity", 1.0 if node_id == source_id else 0.82)
            for port in self._iter_live_ports(item):
                if node_id == source_id and port is start_port:
                    self._safe_scene_call(port, "set_preview_state", "highlight")
                    continue
                if not self.port_is_enabled(node, port.direction, port.port_type):
                    self._safe_scene_call(port, "set_preview_state", "dim")
                    continue
                if start_port.direction == port.direction:
                    self._safe_scene_call(port, "set_preview_state", "dim")
                    continue
                out_port = start_port if start_port.direction == "out" else port
                in_port = port if port.direction == "in" else start_port
                self._safe_scene_call(port, "set_preview_state", "highlight" if can_connect_ports(out_port.node_item.node, in_port.node_item.node, out_port.port_type, in_port.port_type) else "dim")

    def clear_compatible_target_preview(self) -> None:
        self._prune_stale_scene_items()
        for _, item in self._iter_live_node_items():
            self._safe_scene_call(item, "setOpacity", 1.0)
            for port in self._iter_live_ports(item):
                self._safe_scene_call(port, "set_preview_state", "normal")

    def node_has_input_data(self, node: dict[str, Any], port_type: str | None = None) -> bool:
        node_id = str(node.get("id", ""))
        if not node_id:
            return False
        allowed_inputs = set(PORT_RULES.get(str(node.get("type")), {}).get("in", []))
        if port_type:
            allowed_inputs = {port_type} if port_type in allowed_inputs else set()
        if not allowed_inputs:
            return False
        for edge in self.graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if str(edge.get("to", "")) != node_id:
                continue
            to_port = str(edge.get("to_port", ""))
            if to_port in allowed_inputs:
                return True
        return False

    def single_input_port_occupied(self, node: dict[str, Any], port_type: str, exclude_from: str | None = None) -> bool:
        node_type = str(node.get("type", ""))
        if port_type not in SINGLE_INPUT_PORT_RULES.get(node_type, set()):
            return False
        node_id = str(node.get("id", ""))
        if not node_id:
            return False
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

    def port_is_enabled(self, node: dict[str, Any], direction: str, port_type: str) -> bool:
        node_type = str(node.get("type"))
        if direction == "in":
            if port_type in SINGLE_INPUT_PORT_RULES.get(node_type, set()):
                return not self.single_input_port_occupied(node, port_type)
            return True
        if direction == "out":
            dependencies = OUTPUT_PORT_DEPENDENCIES.get(node_type, {}).get("out", {}).get(port_type)
            if dependencies:
                if node_type == "event.publisher":
                    return all(self.node_has_input_data(node, dep) for dep in dependencies)
                if node_type == "event.subscriber":
                    return all(self.node_has_input_data(node, dep) for dep in dependencies) and bool(str(node.get("callback", "")).strip())
                if node_type == "processor.custom":
                    return bool(str(node.get("process", "")).strip()) and any(self.node_has_input_data(node, dep) for dep in dependencies)
                if node_type == "algorithm.custom":
                    return bool(str(node.get("run", "")).strip()) and any(self.node_has_input_data(node, dep) for dep in dependencies)
                return any(self.node_has_input_data(node, dep) for dep in dependencies)
        return True

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

    def edge_pen_for_item(self, edge: dict[str, Any], selected: bool = False, dash_offset: float | None = None) -> QPen:
        kind = str(edge.get("kind", "generic"))
        pen = self.edge_pen(edge)
        try:
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        except AttributeError:
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)

        if kind == "data_flow":
            pen.setStyle(Qt.PenStyle.DashLine if hasattr(Qt, "PenStyle") else Qt.DashLine)
            pen.setDashPattern([10.0, 4.0])
            pen.setWidthF(2.2)
        if dash_offset is not None and kind in {"data_flow", "control_flow", "event"}:
            pen.setDashOffset(dash_offset)
        if selected:
            pen.setColor(QColor("#ffd54f"))
            pen.setWidthF(max(4.0, pen.widthF() + 2.0))
        return pen

    def select_edge(self, edge: dict[str, Any] | None) -> None:
        self.selected_edge_id = str(edge.get("id")) if edge else None
        if edge is None and hasattr(self, "scene") and self.scene is not None:
            self.scene.clearSelection()
            self.clear_compatible_target_preview()
        if edge:
            self.current_node_id = None
            self.focus_node_id = None
            self.apply_focus_mode(None)
        elif not self.focus_node_id:
            self.apply_focus_mode(None)
        for item in self.edge_items:
            is_selected = str(item.edge.get("id")) == self.selected_edge_id
            item.refresh_pen()

    def selected_edge(self) -> dict[str, Any] | None:
        edge_id = getattr(self, "selected_edge_id", None)
        if not edge_id:
            return None
        return next((edge for edge in self.graph.get("edges", []) if str(edge.get("id")) == edge_id), None)

    def refresh_edges(self) -> None:
        for edge in self.edge_items:
            self.scene.removeItem(edge)
        self.edge_items = []
        edges: list[dict[str, Any]] = [edge for edge in self.graph.get("edges", []) if isinstance(edge, dict)]
        for edge in edges:
            src = edge.get("from")
            dst = edge.get("to")
            if src in self.node_items and dst in self.node_items:
                a = self.port_scene_center(src, edge.get("from_port"), "out")
                b = self.port_scene_center(dst, edge.get("to_port"), "in")
                if not a or not b:
                    continue
                line = EdgeItem(edge, self)
                line.update_path(a, b)
                line.refresh_pen()
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

    def tick_edge_animations(self) -> None:
        for edge_item in getattr(self, "edge_items", []):
            kind = str(edge_item.edge.get("kind", "generic"))
            if kind in {"data_flow", "control_flow", "event"}:
                edge_item.advance_flow(0.25 if kind == "data_flow" else 0.8)

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
        runtime_summary = getattr(self, "_runtime_summary_cache", {})
        if node_type == "processor.custom":
            return "行动：实现 process(ctx, in, out)。当它位于 Sensor → Processor → Algorithm/Actuator 数据流上时，codegen 会生成周期执行链；连接到 project.module 只声明模块接口。"
        if node_type == "event.publisher":
            runtime_item = next((item for item in runtime_summary.get("publishers", []) if item.get("id") == str(node.get("id"))), None) if isinstance(runtime_summary, dict) else None
            mode = runtime_item.get("mode") if runtime_item else "manual"
            stage = runtime_item.get("stage") if runtime_item else "unknown"
            return f"行动：连接 topic 和 source 后，codegen 会生成 `app_publish_xxx(...)` 包装函数；若 payload 类型可推断，还会生成 typed/value 版本。当前模式={mode}，挂接阶段={stage}。你可以在 task/module/custom code 中直接调用这些包装函数。"
        if node_type == "event.subscriber":
            return "行动：填写 callback，codegen 会生成 efw_topic_subscribe(...) 绑定；业务逻辑写在订阅回调里。"
        if node_type == "state.machine":
            return "行动：进入状态机页面添加 State / Transition。codegen 会生成 `app_sm_xxx_tick()`、`app_sm_xxx_dispatch_event()`、`app_sm_xxx_transition_to()` 和 `app_sm_xxx_current_state()`。"
        if node_type == "state.transition":
            return "行动：填写 condition，必要时填写 action。event_trigger 必须写成 `topic:<event.topic节点id>` 或 `event:<事件名>`，这样状态机可以通过 `app_dispatch_event(...)` 或 `app_sm_xxx_dispatch_event(...)` 响应事件。"
        if node_type == "project.module":
            runtime_item = next((item for item in runtime_summary.get("project_modules", []) if item.get("module_id") == str(node.get("id"))), None) if isinstance(runtime_summary, dict) else None
            if runtime_item:
                return f"行动：把节点归属到该模块以整理页面；同时会生成可运行的模块壳。当前挂接：自动发布者 {len(runtime_item.get('publishers', []))} 个，状态机 {len(runtime_item.get('state_machines', []))} 个。"
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

    def node_tooltip_text(self, node: dict[str, Any]) -> str:
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        lines = [f"{node_id} [{TYPE_LABELS.get(node_type, node_type)}]"]
        display_name = str(node.get("display_name", "")).strip()
        if display_name:
            lines.append(f"显示名称：{display_name}")
        description = str(node.get("description", "")).strip()
        if description:
            lines.append(description)
        if node_type == "event.publisher":
            runtime_summary = getattr(self, "_runtime_summary_cache", {})
            runtime_item = next((item for item in runtime_summary.get("publishers", []) if item.get("id") == node_id), None) if isinstance(runtime_summary, dict) else None
            mode = runtime_item.get("mode") if runtime_item else ("expr/size" if node.get("data_expr") and node.get("size_expr") else ("source-auto" if node.get("source") else "manual"))
            stage = runtime_item.get("stage") if runtime_item else ("module.poll" if node.get("module") else "root app_update_1ms")
            lines.append(f"自动发布模式：{mode}")
            lines.append(f"挂接阶段：{stage}")
            lines.append(f"最小间隔：{int((runtime_item or {}).get('interval_ms', node.get('interval_ms', 0)) or 0)} ms")
            source_id = (runtime_item or {}).get("source_id") if runtime_item else node.get("source")
            if source_id:
                lines.append(f"来源：{source_id}")
            if node.get("topic"):
                lines.append(f"Topic：{node.get('topic')}")
        lines.append("")
        lines.append(self.node_action_hint(node))
        return "\n".join(lines)

    def select_node(self, node_id: str | None) -> None:
        if node_id is not None:
            self.selected_edge_id = None
            for item in self.edge_items:
                item.setPen(self.edge_pen_for_item(item.edge, selected=False))
            self.clear_compatible_target_preview()
            if hasattr(self, "right_dock") and self.right_dock.isHidden():
                self.right_dock.show()
            if hasattr(self, "right_tabs"):
                self.right_tabs.setCurrentIndex(0)
        self.focus_node_id = node_id
        self.current_node_id = node_id
        self.apply_focus_mode(self.focus_node_id)
        node = self._find_node(node_id) if node_id else None
        if not node and node_id is None:
            node = self.page_source_node()
        if not node:
            if node_id is not None:
                self.current_node_id = None
                self.focus_node_id = None
                self.apply_focus_mode(None)
            self.selected_label.setText("未选择卡片")
            if hasattr(self, "ports_label"):
                self.ports_label.setText("端口：未选择")
            self.node_json_editor.clear()
            if hasattr(self, "clear_property_tables"):
                self.clear_property_tables()
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
        self._normalize_display_fields(template)
        if not self.apply_page_ownership(template):
            return
        display_name = self._prompt_display_name(node_type, self._default_display_name(template, node_type))
        if display_name is None:
            return
        existing = {node.get("id") for node in self.graph.get("nodes", [])}
        template["display_name"] = display_name
        new_id = self._derive_node_id(display_name, str(template.get("id", node_type)), existing, node_type, template)
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
