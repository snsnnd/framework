#!/usr/bin/env python3
"""Callback preview and stub generation mixin for Studio editor."""

from __future__ import annotations

import importlib.util

from studio.qt_compat import (
    QMessageBox,
)

from codegen.graph import CALLBACK_SIGNATURES, NODE_CONTRACTS, callback_signature


class CallbackMixin:
    def source_files_for_preview(self) -> list[dict[str, str]]:
        return [item for item in self.graph.get("custom_files", []) + self.graph.get("board_adapters", []) if str(item.get("path", "")).endswith((".c", ".h"))]

    def callback_names_for_node(self, node: dict[str, object]) -> list[str]:
        names = []
        contract = NODE_CONTRACTS.get(str(node.get("type")), {})
        for field in contract.get("callbacks", {}):
            value = str(node.get(field, "")).strip()
            if value:
                names.append(value)
        if node.get("type") == "task.periodic" and node.get("call"):
            names.append(str(node.get("call")))
        return names

    def find_function_snippet(self, content: str, name: str) -> str | None:
        span = self.find_function_span(content, name)
        if not span:
            return None
        return content[span[0]:span[1]].strip()

    def find_function_span(self, content: str, name: str) -> tuple[int, int] | None:
        marker = content.find(name + "(")
        if marker < 0:
            marker = content.find(name + " (")
        if marker < 0:
            return None
        start = content.rfind("\n", 0, marker) + 1
        brace = content.find("{", marker)
        if brace < 0:
            end = content.find(";", marker)
            return (start, end + 1) if end >= 0 else None
        depth = 0
        for index in range(brace, len(content)):
            if content[index] == "{":
                depth += 1
            elif content[index] == "}":
                depth -= 1
                if depth == 0:
                    return (start, index + 1)
        return (start, len(content))

    def refresh_callback_selector(self, node: dict[str, object]) -> None:
        if not hasattr(self, "callback_select"):
            return
        self.callback_select.blockSignals(True)
        self.callback_select.clear()
        names = self.callback_names_for_node(node)
        self.callback_select.addItems(names or ["无回调"])
        self.callback_select.blockSignals(False)
        self.load_selected_callback_implementation(self.callback_select.currentText())

    def refresh_callback_preview(self, node: dict[str, object]) -> None:
        if not hasattr(self, "callback_preview_output"):
            return
        names = self.callback_names_for_node(node)
        if not names:
            self.callback_preview_output.setPlainText("当前卡片没有声明回调函数。")
            return
        chunks = []
        files = self.source_files_for_preview()
        for name in names:
            found = False
            for item in files:
                snippet = self.find_function_snippet(str(item.get("content", "")), name)
                if snippet:
                    chunks.append(f"// {item.get('path')} :: {name}\n{snippet}")
                    found = True
                    break
            if not found:
                chunks.append(f"// 未找到实现：{name}\n// 可到 Code 页点击“一键生成缺失回调”。")
        self.callback_preview_output.setPlainText("\n\n".join(chunks))

    def callback_stub_by_name(self, name: str) -> str:
        for requirement in self.callback_requirements():
            if requirement["name"] == name:
                return self.callback_stub(requirement).strip()
        return f"efw_status_t {name}(void) {{\n  return EFW_OK;\n}}"

    def load_selected_callback_implementation(self, name: str) -> None:
        if not hasattr(self, "callback_preview_output"):
            return
        if not name or name == "无回调":
            self.callback_preview_output.setPlainText("当前卡片没有声明回调函数。")
            return
        for item in self.source_files_for_preview():
            snippet = self.find_function_snippet(str(item.get("content", "")), name)
            if snippet:
                self.callback_preview_output.setPlainText(snippet)
                return
        self.callback_preview_output.setPlainText(self.callback_stub_by_name(name))

    def save_selected_callback_implementation(self) -> None:
        if not hasattr(self, "callback_select") or not hasattr(self, "callback_preview_output"):
            return
        name = self.callback_select.currentText().strip()
        if not name or name == "无回调":
            return
        implementation = self.callback_preview_output.toPlainText().strip() + "\n"
        files = self.graph.setdefault("custom_files", [])
        target = next((item for item in files if item.get("path") == "app_custom.c"), None)
        if target is None:
            target = {"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"}
            files.insert(0, target)
        content = str(target.get("content", ""))
        span = self.find_function_span(content, name)
        self.push_undo()
        if span:
            content = content[:span[0]] + implementation + content[span[1]:]
        else:
            content = content.rstrip() + "\n\n" + implementation
        target["content"] = content
        self.current_code_index = files.index(target)
        self.refresh_code_list()
        self.select_code_file(self.current_code_index)
        self.refresh_json_editor()

    def existing_custom_code(self) -> str:
        parts = [item.get("content", "") for item in self.graph.get("custom_files", [])]
        parts.extend(item.get("content", "") for item in self.graph.get("board_adapters", []))
        return "\n".join(parts)

    def callback_requirements(self) -> list[dict[str, str]]:
        requirements: list[dict[str, str]] = []
        for node in self.graph.get("nodes", []):
            contract = NODE_CONTRACTS.get(str(node.get("type")), {})
            for field, signature_key in contract.get("callbacks", {}).items():
                name = str(node.get(field, "")).strip()
                if name:
                    requirements.append({"owner": str(node.get("id")), "type": str(node.get("type")), "field": field, "name": name, "signature_key": signature_key})
        for task in self.graph.get("tasks", []):
            name = str(task.get("call", "")).strip()
            if name:
                requirements.append({"owner": str(task.get("id")), "type": "task.periodic", "field": "call", "name": name, "signature_key": "task.call"})
        return requirements

    def missing_callback_requirements(self) -> list[dict[str, str]]:
        existing_content = self.existing_custom_code()
        return [item for item in self.callback_requirements() if item["name"] not in existing_content]

    def callback_stub(self, requirement: dict[str, str]) -> str:
        name = requirement["name"]
        signature_key = requirement["signature_key"]
        params = CALLBACK_SIGNATURES.get(signature_key, "void")
        if signature_key == "topic.callback":
            return f"void {name}({params}) {{\n  EFW_UNUSED(topic_id);\n  EFW_UNUSED(data);\n  EFW_UNUSED(size);\n  EFW_UNUSED(user);\n}}\n"
        if signature_key == "condition":
            return f"int {name}(void) {{\n  /* TODO: return non-zero when this condition should pass. */\n  return 0;\n}}\n"
        body_lines = []
        if "ctx" in params:
            body_lines.append("  EFW_UNUSED(ctx);")
        if "buf" in params:
            body_lines.append("  EFW_UNUSED(buf);")
        if "len" in params:
            body_lines.append("  EFW_UNUSED(len);")
        if "actual" in params:
            if signature_key == "hal.write":
                body_lines.append("  if (actual) *actual = len;")
            else:
                body_lines.append("  if (actual) *actual = 0;")
        if "out" in params:
            body_lines.append("  EFW_UNUSED(out);")
        if "cmd" in params:
            body_lines.append("  EFW_UNUSED(cmd);")
        if "const void *in" in params or "void *in" in params:
            body_lines.append("  EFW_UNUSED(in);")
        if "uint32_t cmd" in params:
            body_lines.append("  EFW_UNUSED(cmd);")
        if "arg" in params:
            body_lines.append("  EFW_UNUSED(arg);")
        body_lines.append("  return EFW_OK;")
        return f"efw_status_t {name}({params}) {{\n" + "\n".join(body_lines) + "\n}\n"

    def callback_stubs(self) -> list[str]:
        seen: set[str] = set()
        stubs: list[str] = []
        for requirement in self.missing_callback_requirements():
            name = requirement["name"]
            if name in seen:
                continue
            seen.add(name)
            stubs.append(self.callback_stub(requirement))
        return stubs

    def refresh_callback_gap_view(self) -> None:
        if not hasattr(self, "callback_gap_output"):
            return
        missing = self.missing_callback_requirements()
        
        # Build HTML output
        html = []
        html.append('<div style="font-family: Consolas, monospace; font-size: 12px;">')
        
        # Title
        html.append('<div style="margin-bottom: 12px;">')
        html.append('<span style="color: #E0E0E0; font-weight: bold; font-size: 14px;">缺失回调 / 用户代码行动项</span>')
        html.append('</div>')
        
        if missing:
            # Missing callbacks section
            html.append('<div style="margin-bottom: 12px;">')
            html.append('<span style="color: #FFEB3B; font-weight: bold;">📝 需要实现的回调</span>')
            html.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for item in missing:
                signature = callback_signature(item["signature_key"])
                name = item.get('name', '')
                owner = item.get('owner', '')
                html.append(f'<li style="color: #FFF9C4; margin: 4px 0;">')
                html.append(f'<b>{name}</b> <span style="color: #B0BEC5;">({signature})</span>')
                html.append(f'<br><span style="color: #78909C; font-size: 11px;">来自: {owner} → 建议生成到 app_custom.c</span>')
                html.append(f'</li>')
            html.append('</ul></div>')
        else:
            html.append('<div style="color: #4CAF50; margin-bottom: 12px;">✅ 当前没有缺失回调。</div>')
        
        # Documentation/organization nodes
        doc_nodes = [node for node in self.graph.get("nodes", []) if not NODE_CONTRACTS.get(str(node.get("type")), {}).get("generated")]
        if doc_nodes:
            html.append('<div style="margin-bottom: 12px;">')
            html.append('<span style="color: #2196F3; font-weight: bold;">ℹ️ 仅说明/组织节点</span>')
            html.append('<ul style="margin: 4px 0 0 20px; padding: 0;">')
            for node in doc_nodes:
                node_id = node.get('id', '')
                node_type = node.get('type', '')
                hint = self.node_action_hint(node)
                html.append(f'<li style="color: #90CAF9; margin: 2px 0;">')
                html.append(f'<b>{node_id}</b> <span style="color: #78909C;">[{node_type}]</span>')
                if hint:
                    html.append(f'<br><span style="color: #78909C; font-size: 11px;">{hint}</span>')
                html.append(f'</li>')
            html.append('</ul></div>')
        
        html.append('</div>')
        
        self.callback_gap_output.setHtml("\n".join(html))

    def callback_stubs_legacy(self) -> list[str]:
        stubs: list[str] = []
        existing_content = self.existing_custom_code()

        def has_symbol(name: str) -> bool:
            return bool(name) and name in existing_content

        for node in self.graph.get("nodes", []):
            ntype = node.get("type")
            for field, signature, body in [
                ("init", "efw_status_t {name}(void *ctx)", "    EFW_UNUSED(ctx);\n    return EFW_OK;"),
                ("read", "efw_status_t {name}(void *ctx, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
                ("write", "efw_status_t {name}(void *ctx, const void *cmd)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(cmd);\n    return EFW_OK;"),
                ("poll", "efw_status_t {name}(void *ctx)", "    EFW_UNUSED(ctx);\n    return EFW_OK;"),
                ("run", "efw_status_t {name}(void *ctx, const void *in, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(in);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
                ("process", "efw_status_t {name}(void *ctx, const void *in, void *out)", "    EFW_UNUSED(ctx);\n    EFW_UNUSED(in);\n    EFW_UNUSED(out);\n    return EFW_OK;"),
            ]:
                name = node.get(field)
                if name and not has_symbol(str(name)):
                    if ntype == "hal.custom" and field == "read":
                        stubs.append(f"efw_status_t {name}(void *ctx, void *buf, uint16_t len, uint16_t *actual) {{\n    EFW_UNUSED(ctx);\n    EFW_UNUSED(buf);\n    EFW_UNUSED(len);\n    if (actual) *actual = 0;\n    return EFW_OK;\n}}\n")
                    elif ntype == "hal.custom" and field == "write":
                        stubs.append(f"efw_status_t {name}(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {{\n    EFW_UNUSED(ctx);\n    EFW_UNUSED(buf);\n    if (actual) *actual = len;\n    return EFW_OK;\n}}\n")
                    elif ntype == "module.custom" and field == "poll":
                        source_publishers = [item for item in self.graph.get("nodes", []) if item.get("type") == "event.publisher" and item.get("source") == node.get("id")]
                        hint = ""
                        if source_publishers:
                            source_id = str(node.get("id"))
                            helper_id = source_id.replace("-", "_")
                            hint = (
                                f"    /* This module is the source of {len(source_publishers)} event.publisher node(s).\n"
                                f"       To feed generated auto-publishers, write your latest output into the generated cache helper, for example:\n"
                                f"       app_source_{helper_id}_store(...);\n"
                                f"       app_source_{helper_id}_store_typed(...);\n"
                                f"       app_source_{helper_id}_store_value(...);\n"
                                f"    */\n"
                            )
                        stubs.append(f"efw_status_t {name}(void *ctx) {{\n    EFW_UNUSED(ctx);\n{hint}    return EFW_OK;\n}}\n")
                    else:
                        stubs.append(signature.format(name=name) + " {\n" + body + "\n}\n")
            if ntype == "event.subscriber" and node.get("callback") and not has_symbol(str(node.get("callback"))):
                name = node.get("callback")
                stubs.append(f"void {name}(uint16_t topic_id, const void *data, uint16_t size, void *user) {{\n    EFW_UNUSED(topic_id);\n    EFW_UNUSED(data);\n    EFW_UNUSED(size);\n    EFW_UNUSED(user);\n}}\n")
            if ntype == "state.state":
                for field in ["on_enter", "on_update", "on_exit"]:
                    name = node.get(field)
                    if name and not has_symbol(str(name)):
                        stubs.append(f"efw_status_t {name}(void *ctx) {{\n    EFW_UNUSED(ctx);\n    return EFW_OK;\n}}\n")
            if ntype == "state.transition" and node.get("condition") and not has_symbol(str(node.get("condition"))):
                name = node.get("condition")
                stubs.append(f"int {name}(void) {{\n    return 0;\n}}\n")
            if ntype == "state.transition" and node.get("action") and not has_symbol(str(node.get("action"))):
                name = node.get("action")
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        for task in self.graph.get("tasks", []) + [n for n in self.graph.get("nodes", []) if n.get("type") == "task.periodic"]:
            name = task.get("call")
            if name and not has_symbol(str(name)):
                stubs.append(f"efw_status_t {name}(void) {{\n    return EFW_OK;\n}}\n")
        return stubs

    def condition_stubs(self) -> list[str]:
        self.apply_code_file(record_history=False)
        existing_content = "\n".join(file.get("content", "") for file in self.graph.get("custom_files", []))
        stubs: list[str] = []
        for node in self.graph.get("nodes", []):
            if node.get("type") == "state.transition":
                name = str(node.get("condition", "")).strip()
                if name and name not in existing_content:
                    stubs.append(f"int {name}(void) {{\n  /* TODO: return non-zero when this condition should pass. */\n  return 0;\n}}\n")
        return stubs

    def generate_condition_callbacks(self) -> None:
        stubs = self.condition_stubs()
        if not stubs:
            QMessageBox.information(self, "条件函数", "没有发现需要生成的条件函数。")
            return
        files = self.graph.setdefault("custom_files", [])
        if not files:
            files.append({"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"})
        self.push_undo()
        files[0]["content"] = files[0].get("content", "") + "\n/* Auto-generated condition stubs */\n" + "\n".join(stubs)
        self.current_code_index = 0
        self.refresh_code_list()
        self.select_code_file(0)
        self.refresh_json_editor()
        QMessageBox.information(self, "条件函数", f"已生成 {len(stubs)} 个条件函数 stub。")

    def generate_missing_callbacks(self) -> None:
        self.apply_code_file(record_history=False)
        stubs = self.callback_stubs()
        if not stubs:
            QMessageBox.information(self, "缺失回调", "没有发现需要生成的缺失回调。")
            return
        files = self.graph.setdefault("custom_files", [])
        if not files:
            files.append({"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n\n"})
        self.push_undo()
        files[0]["content"] = files[0].get("content", "") + "\n/* Auto-generated missing callback stubs */\n" + "\n".join(stubs)
        self.current_code_index = 0
        self.refresh_code_list()
        self.refresh_json_editor()
        QMessageBox.information(self, "缺失回调", f"已生成 {len(stubs)} 个回调 stub 到 {files[0].get('path')}。")
