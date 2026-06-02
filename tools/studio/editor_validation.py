#!/usr/bin/env python3
"""Validation, mapping, and schedule preview mixin for the Studio editor."""

from __future__ import annotations

from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor
    from PyQt6.QtWidgets import QListWidgetItem, QMessageBox
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor
    from PyQt5.QtWidgets import QListWidgetItem, QMessageBox
else:
    Qt = QBrush = QColor = QListWidgetItem = QMessageBox = object

from codegen import c_ident
from codegen.validate import validate_graph
from codegen.graph import NODE_CONTRACTS, apply_pair_semantics, callback_signature, node_generation_label, semantic_edge_kind
from studio.editor_registry import TYPE_LABELS
from studio.model import GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS


class ValidationMixin:
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
        nodes_by_id = {node.get("id"): node for node in self.graph.get("nodes", []) if node.get("id")}
        runtime_types = {"sensor.custom", "sensor.line_tracking", "processor.custom", "algorithm.pid", "algorithm.custom", "actuator.motor", "actuator.custom"}
        flow_owned: set[str] = set()
        for flow in self.graph.get("flows", []):
            if flow.get("type") == "control.line_follower":
                flow_owned.update(str(flow.get(key)) for key in ("sensor", "pid", "left_motor", "right_motor") if flow.get(key))
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
        starts = [str(node["id"]) for node in self.graph.get("nodes", []) if node.get("type") in {"sensor.custom", "sensor.line_tracking"} and node.get("id") in adjacency]
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
        if node_id:
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
        except Exception as exc:  # noqa: BLE001
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
        errors = [item for item in messages if item.startswith("❌")]
        warnings = [item for item in messages if item.startswith("⚠️")]
        next_step = "可以直接生成 application。" if ok else "先处理红色错误，再重新校验；黄色警告建议在生成前处理。"
        summary_lines = [
            "校验摘要",
            f"- 错误：{len(errors)}",
            f"- 警告：{len(warnings)}",
            f"- 结论：{'可生成' if ok else '需修正后再生成'}",
            f"- 下一步：{next_step}",
            "",
        ]
        text = "\n".join(summary_lines + messages)
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

    def _connect_pair(self, src: dict[str, Any], dst: dict[str, Any]) -> bool:
        connected = apply_pair_semantics(src, dst, self.graph, c_ident_func=c_ident, overwrite=True)
        if connected and src.get("type") == "custom.code":
            QMessageBox.information(self, "Connect cards", "Use the Code tab to implement callbacks named by the selected custom card.")
        return connected
