#!/usr/bin/env python3
"""Validation, mapping, and schedule preview mixin for the Studio editor."""

from __future__ import annotations

from typing import Any

import importlib.util

from studio.qt_compat import (
    Qt,
    QBrush, QColor,
    QListWidgetItem, QMessageBox,
)

from codegen import c_ident
from codegen.generator import build_runtime_summary
from codegen.graph import NODE_CONTRACTS, apply_pair_semantics, callback_signature, node_generation_label, semantic_edge_kind
from studio.editor_registry import TYPE_LABELS
from studio.model import GENERATED_APPLICATION_TREE, NODE_GENERATION_STATUS
from tools.api.graph import validate_graph_data


class ValidationMixin:
    def runtime_summary(self) -> dict[str, Any]:
        try:
            summary = build_runtime_summary(validate_graph_data(self.graph))
        except Exception:
            summary = {}
        self._runtime_summary_cache = summary
        return summary

    def action_for_validation_message(self, message: str, target: str | None) -> str:
        if "Pin Planner 冲突" in message:
            return "打开高级面板里的 Board Profile / Pin Planner，修改重复资源后再重新校验。"
        if ".condition 为空" in message:
            return f"定位到节点 {target or 'state.transition'}，在属性表单里填写 condition 函数名，然后到代码补齐页创建该函数。"
        if message.startswith("❌") and target:
            return f"点击左侧问题列表定位到节点 {target}，先修正属性表单中的红色项，再重新校验。"
        if message.startswith("⚠️") and target:
            return f"点击左侧问题列表定位到节点 {target}，确认该警告是否需要处理；一般建议在生成前处理。"
        if message.startswith("❌ Graph 校验失败"):
            return "先根据失败信息修正引用、周期或必填字段；修完后再次点击“立即校验”。"
        return "如果不确定，从“项目总览”按步骤继续：模块装配 -> 关系视图 -> 代码补齐 -> 生成发布。"

    def refresh_mapping_view(self) -> None:
        if not hasattr(self, "mapping_output"):
            return
        lines = ["Graph → Generated Code 映射（来自 codegen 契约）", ""]
        runtime_summary = self.runtime_summary()
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
        publishers = runtime_summary.get("publishers", []) if isinstance(runtime_summary, dict) else []
        if publishers:
            lines.append("")
            lines.append("自动发布缓存 / 来源")
            for item in publishers:
                node = item.get("node", {})
                source = str(item.get("source_id") or "(无 source)")
                lines.append(f"- {item.get('id')} → topic={node.get('topic')} | source={source} | mode={item.get('mode')} | stage={item.get('stage')} | interval_ms={item.get('interval_ms')}")
        self.mapping_output.setPlainText("\n".join(lines))

    def refresh_structure_view(self) -> None:
        if not hasattr(self, "structure_output"):
            return
        runtime_summary = self.runtime_summary()
        module_runtime = runtime_summary.get("project_modules", []) if isinstance(runtime_summary, dict) else []
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
            runtime_item = next((item for item in module_runtime if item.get("module_id") == mid), None)
            if runtime_item:
                lines.append(f"  · 自动发布者：{len(runtime_item.get('publishers', []))}")
                lines.append(f"  · 状态机：{len(runtime_item.get('state_machines', []))}")
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
        plan = self.runtime_plan_preview()
        
        # Build HTML output
        html = []
        html.append('<div style="font-family: Consolas, monospace; font-size: 12px;">')
        
        # Title
        html.append(f'<div style="color: #E0E0E0; font-weight: bold; margin-bottom: 12px;">运行计划预览（tick = {tick} ms）</div>')
        
        if plan:
            # Show timeline visualization
            html.append('<div style="margin-bottom: 12px;">')
            html.append('<span style="color: #2196F3; font-weight: bold;">⏱ 调度时间线</span>')
            
            for period in sorted(plan):
                # Period header
                html.append(f'<div style="margin: 8px 0 4px 0; color: #FFEB3B; font-weight: bold;">{period}ms 周期:</div>')
                html.append('<ul style="margin: 0 0 0 20px; padding: 0;">')
                
                for order, label in sorted(plan[period], key=lambda item: (item[0], item[1])):
                    # Color based on type
                    if "dataflow" in label.lower():
                        color = "#4FC3F7"  # Light blue
                    elif "task" in label.lower():
                        color = "#81C784"  # Green
                    elif "state" in label.lower():
                        color = "#CE93D8"  # Purple
                    elif "module" in label.lower():
                        color = "#FFB74D"  # Orange
                    else:
                        color = "#E0E0E0"  # White
                    
                    html.append(f'<li style="color: {color}; margin: 2px 0;">{order}. {label}</li>')
                
                html.append('</ul>')
            html.append('</div>')
        else:
            html.append('<div style="color: #78909C; margin-bottom: 12px;">暂无自动 dataflow、flow、task、state machine 或 module poll。</div>')
        
        # Legend
        html.append('<div style="margin-top: 16px; padding-top: 8px; border-top: 1px solid #242D40;">')
        html.append('<span style="color: #90A4AE; font-weight: bold;">调度语义：</span>')
        html.append('<ol style="margin: 4px 0 0 20px; padding: 0; color: #B0BEC5;">')
        html.append('<li><span style="color: #4FC3F7;">自动 dataflow pipelines</span></li>')
        html.append('<li><span style="color: #81C784;">task.periodic</span></li>')
        html.append('<li><span style="color: #CE93D8;">state.machine tick</span></li>')
        html.append('<li><span style="color: #FFB74D;">efw_module_poll_all()</span></li>')
        html.append('</ol>')
        html.append('<div style="color: #78909C; margin-top: 8px; font-size: 11px;">说明：同一周期按编号顺序生成；多个 dataflow 仅按发现顺序执行。</div>')
        html.append('</div>')
        
        html.append('</div>')
        
        self.schedule_output.setHtml("\n".join(html))

    def generation_readiness_lines(self) -> list[str]:
        missing_callbacks = self.missing_callback_requirements()
        doc_nodes = [node for node in self.graph.get("nodes", []) if not NODE_CONTRACTS.get(str(node.get("type")), {}).get("generated")]
        partial_nodes = [node for node in self.graph.get("nodes", []) if node_generation_label(str(node.get("type"))) == "部分生成"]
        hardware_mock_nodes = [node for node in self.graph.get("nodes", []) if node.get("type") in {"hal.gpio_line_input", "actuator.motor"}]
        custom_hardware_nodes = [node for node in self.graph.get("nodes", []) if node.get("type") in {"hal.custom", "sensor.custom", "actuator.custom"}]
        runtime_summary = self.runtime_summary()
        publishers = runtime_summary.get("publishers", []) if isinstance(runtime_summary, dict) else []
        state_machines = runtime_summary.get("state_machines", []) if isinstance(runtime_summary, dict) else []
        lines = ["生成就绪度："]
        lines.append(f"- 缺失用户回调：{len(missing_callbacks)} 个")
        lines.append(f"- 部分生成节点：{len(partial_nodes)} 个")
        lines.append(f"- 仅说明/组织节点：{len(doc_nodes)} 个")
        lines.append(f"- 运行时发布者：{len(publishers)} 个")
        lines.append(f"- 运行时状态机：{len(state_machines)} 个")
        lines.append(f"- host mock 硬件节点：{len(hardware_mock_nodes)} 个")
        lines.append(f"- 需要真实 BSP/board_adapters 关注的自定义硬件节点：{len(custom_hardware_nodes)} 个")
        if missing_callbacks:
            lines.append("- 下一步：到 Code 页点击“一键生成缺失回调”，再补业务逻辑。")
        if any(node.get("type") == "event.publisher" for node in doc_nodes):
            lines.append("- 注意：event.publisher 现在会生成 app_publish_xxx(...) 包装函数；如果 payload 类型可推断，还会生成 typed/value 版本。你可以在 task/module/custom code 中直接调用这些包装函数。")
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
            validate_graph_data(self.graph)
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
        
        # Format output with HTML for better styling
        html_lines = []
        html_lines.append('<div style="font-family: Consolas, monospace; font-size: 12px;">')
        
        # Summary section
        errors = [item for item in messages if item.startswith("❌")]
        warnings = [item for item in messages if item.startswith("⚠️")]
        infos = [item for item in messages if item.startswith("ℹ️")]
        successes = [item for item in messages if item.startswith("✅")]
        
        # Status header
        if ok:
            html_lines.append('<div style="background: #1a3a1a; border: 1px solid #2d5a2d; border-radius: 6px; padding: 10px; margin-bottom: 12px;">')
            html_lines.append('<span style="color: #4CAF50; font-weight: bold;">✅ 可以生成 Application</span>')
            html_lines.append('</div>')
        else:
            html_lines.append('<div style="background: #3a1a1a; border: 1px solid #5a2d2d; border-radius: 6px; padding: 10px; margin-bottom: 12px;">')
            html_lines.append(f'<span style="color: #F44336; font-weight: bold;">❌ 需修正后再生成 ({len(errors)} 个错误, {len(warnings)} 个警告)</span>')
            html_lines.append('</div>')
        
        # Errors section
        if errors:
            html_lines.append('<div style="margin-bottom: 8px;">')
            html_lines.append('<span style="color: #F44336; font-weight: bold;">❌ 错误</span>')
            html_lines.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for msg in errors:
                html_lines.append(f'<li style="color: #FFB3B3; margin: 2px 0;">{msg[2:]}</li>')
            html_lines.append('</ul></div>')
        
        # Warnings section
        if warnings:
            html_lines.append('<div style="margin-bottom: 8px;">')
            html_lines.append('<span style="color: #FF9800; font-weight: bold;">⚠️ 警告</span>')
            html_lines.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for msg in warnings:
                html_lines.append(f'<li style="color: #FFE0A3; margin: 2px 0;">{msg[2:]}</li>')
            html_lines.append('</ul></div>')
        
        # Missing callbacks section
        missing_callbacks = self.missing_callback_requirements()
        if missing_callbacks:
            html_lines.append('<div style="margin-bottom: 8px;">')
            html_lines.append('<span style="color: #FFEB3B; font-weight: bold;">📝 缺失回调 (需要实现)</span>')
            html_lines.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for req in missing_callbacks[:10]:
                name = req.get("name", "")
                sig = req.get("signature", "")
                html_lines.append(f'<li style="color: #FFF9C4; margin: 2px 0;"><b>{name}</b> <span style="color: #B0BEC5;">({sig})</span></li>')
            if len(missing_callbacks) > 10:
                html_lines.append(f'<li style="color: #B0BEC5;">... 还有 {len(missing_callbacks) - 10} 个</li>')
            html_lines.append('</ul></div>')
        
        # Info section
        if infos:
            html_lines.append('<div style="margin-bottom: 8px;">')
            html_lines.append('<span style="color: #2196F3; font-weight: bold;">ℹ️ 信息</span>')
            html_lines.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for msg in infos:
                html_lines.append(f'<li style="color: #90CAF9; margin: 2px 0;">{msg[2:]}</li>')
            html_lines.append('</ul></div>')
        
        html_lines.append('</div>')
        
        text = "\n".join(html_lines)
        self.validation_messages = messages
        self.validation_targets = [self._validation_target_from_message(message) for message in messages]
        if hasattr(self, "release_output"):
            self.release_output.setHtml(text)
        if hasattr(self, "validation_output"):
            # Also use HTML for validation_output
            self.validation_output.setHtml(text)
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
                grouped_action = self.action_for_validation_message(target_messages[0], target)
                header.setToolTip(f"点击定位到卡片：{target}\n\n建议动作：{grouped_action}")
                header.setBackground(QBrush(QColor("#263746")))
                header.setForeground(QBrush(QColor("#ffffff")))
                self.validation_list.addItem(header)
                for message in target_messages:
                    child = QListWidgetItem("  " + message)
                    child.setData(role, target)
                    child.setToolTip(f"点击定位到卡片：{target}\n\n建议动作：{self.action_for_validation_message(message, target)}")
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
