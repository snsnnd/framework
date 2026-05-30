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


def page_for_node(node: dict[str, Any]) -> Page | None:
    node_type = node.get("type")
    node_id = str(node.get("id", ""))
    if not node_id:
        return None
    if node_type == "project.module":
        return {"key": page_key("module", node_id), "kind": "module", "id": node_id, "title": f"模块:{node_id}", "mode": "module"}
    if node_type == "state.machine":
        return {"key": page_key("state", node_id), "kind": "state", "id": node_id, "title": f"状态机:{node_id}", "mode": "state_machine"}
    if node_type == "event.topic":
        return {"key": page_key("comm", node_id), "kind": "comm", "id": node_id, "title": f"通信:{node_id}", "mode": "pubsub"}
    return None


def page_title(page: Page) -> str:
    return page.get("title") or page.get("key", "root")


def visible_nodes_for_page(graph: dict[str, Any], page: Page | None) -> list[dict[str, Any]]:
    if not page or page.get("kind") == "root":
        return graph.get("nodes", [])
    kind = page.get("kind")
    node_id = page.get("id")
    nodes = graph.get("nodes", [])
    if kind == "module":
        return [node for node in nodes if node.get("id") == node_id or node.get("module") == node_id or node.get("parent") == node_id]
    if kind == "state":
        return [node for node in nodes if node.get("id") == node_id or node.get("machine") == node_id]
    if kind == "comm":
        return [node for node in nodes if node.get("id") == node_id or node.get("topic") == node_id]
    return nodes


def page_hint(page: Page | None) -> str:
    if not page or page.get("kind") == "root":
        return "根项目：通用蓝图视图，双击模块/状态机/Topic 可打开专用页面。"
    if page.get("kind") == "module":
        return "模块页面：显示模块接口与内部节点；当前仍保存到同一 Graph，后续可升级为独立 subgraph 编译。"
    if page.get("kind") == "state":
        return "状态机页面：重点表达 State → Transition → State，端口已区分 machine/from/to。"
    if page.get("kind") == "comm":
        return "通信页面：围绕 Topic 展示 Publisher / Subscriber 关系，适合检查发布订阅拓扑。"
    return "蓝图页面"
