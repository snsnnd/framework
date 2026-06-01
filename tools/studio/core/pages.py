"""Page/view helpers for EFW Studio.

These helpers describe VS Code-like editor tabs without importing PyQt.  A page
is a lightweight view over the graph today, and it also carries enough metadata
to evolve project.module cards into true nested subgraphs later.
"""

from __future__ import annotations

from typing import Any

Page = dict[str, str]


def page_key(kind: str, node_id: str = "") -> str:
    return "root" if kind == "root" else f"{kind}:{node_id}"


def root_page() -> Page:
    return {"key": "root", "kind": "root", "id": "", "title": "根项目", "mode": "blueprint"}


def node_display_name(node: dict[str, Any]) -> str:
    return str(node.get("display_name") or node.get("description") or node.get("id") or "未命名")


def page_for_node(node: dict[str, Any]) -> Page | None:
    node_type = node.get("type")
    node_id = str(node.get("id", ""))
    if not node_id:
        return None
    if node_type == "project.module":
        return {"key": page_key("module", node_id), "kind": "module", "id": node_id, "title": f"模块:{node_display_name(node)}", "mode": "module"}
    if node_type == "state.machine":
        return {"key": page_key("state", node_id), "kind": "state", "id": node_id, "title": f"状态机:{node_display_name(node)}", "mode": "state_machine"}
    if node_type == "event.topic":
        return {"key": page_key("comm", node_id), "kind": "comm", "id": node_id, "title": f"通信:{node_display_name(node)}", "mode": "pubsub"}
    return None


def page_title(page: Page) -> str:
    return page.get("title") or page.get("key", "root")


def is_root_visible_node(node: dict[str, Any]) -> bool:
    node_type = node.get("type")
    if node_type == "project.module":
        return not node.get("parent")
    if node_type == "custom.card":
        return node.get("scope", "root") == "root" and not node.get("module")
    if node_type in {"event.topic", "event.publisher", "event.subscriber"}:
        return not node.get("module")
    return False


def visible_nodes_for_page(graph: dict[str, Any], page: Page | None) -> list[dict[str, Any]]:
    nodes = graph.get("nodes", [])
    if not page or page.get("kind") == "root":
        return [node for node in nodes if is_root_visible_node(node)]
    kind = page.get("kind")
    node_id = page.get("id")
    if kind == "module":
        return [node for node in nodes if node.get("module") == node_id or node.get("parent") == node_id]
    if kind == "state":
        scope = page.get("key")
        return [node for node in nodes if node.get("id") == node_id or node.get("machine") == node_id or (node.get("type") == "custom.card" and node.get("scope") == scope)]
    if kind == "comm":
        scope = page.get("key")
        return [node for node in nodes if node.get("topic") == node_id or (node.get("type") == "custom.card" and node.get("scope") == scope)]
    return nodes


def page_hint(page: Page | None) -> str:
    if not page or page.get("kind") == "root":
        return "系统模块视图：只展示 project.module、模块公共输入/输出和事件发布订阅关系；双击模块进入内部实现视图。"
    if page.get("kind") == "module":
        return "模块内部视图：可放 HAL / Sensor / processor.custom / Algorithm / Actuator / Task / StateMachine / CustomCode；新卡片会自动归属当前模块。"
    if page.get("kind") == "state":
        return "状态机页面：只建议添加 State / Transition；新状态或转换会自动绑定当前状态机。"
    if page.get("kind") == "comm":
        return "通信页面：围绕 Topic 展示 Publisher / Subscriber；新发布者/订阅者会自动绑定当前 Topic。"
    return "蓝图页面"
