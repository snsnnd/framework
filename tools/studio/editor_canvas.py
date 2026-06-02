#!/usr/bin/env python3
"""Canvas rendering items and helpers for the EFW visual editor."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import QMimeData, QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QPen
    from PyQt6.QtWidgets import (
        QGraphicsItem, QGraphicsLineItem, QGraphicsRectItem,
        QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsTextItem,
        QGraphicsView, QListWidget, QListWidgetItem,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import QMimeData, QPointF, Qt
    from PyQt5.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QPen
    from PyQt5.QtWidgets import (
        QGraphicsItem, QGraphicsLineItem, QGraphicsRectItem,
        QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsTextItem,
        QGraphicsView, QListWidget, QListWidgetItem,
    )
    QT_LIB = "PyQt5"
else:
    QGraphicsItem = QGraphicsRectItem = QGraphicsView = object
    QListWidget = object
    QT_LIB = "missing"

from codegen.graph import NODE_CONTRACTS, PORT_COLORS, PORT_LABELS, PORT_RULES
from studio.core import node_summary, page_for_node
from studio.editor_registry import NODE_TEMPLATES, TYPE_LABELS

if TYPE_CHECKING:
    from studio.editor import VisualEditorWindow


# ---------------------------------------------------------------------------
#  Type label mapping (used by both canvas rendering and editor UI)
# ---------------------------------------------------------------------------

def parse_form_value(text: str) -> Any:
    value = text.strip()
    if value == "":
        return ""
    if value == "null":
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        if value.startswith(("{", "[")):
            return json.loads(value)
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return text
    except json.JSONDecodeError:
        return text


def form_value_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def card_display_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("display_name") or node.get("title") or node.get("id") or "未命名")


def card_description(node: dict[str, Any]) -> str:
    return str(node.get("description") or node.get("note") or NODE_CONTRACTS.get(str(node.get("type")), {}).get("boundary", ""))


def card_port_lines(node: dict[str, Any]) -> list[str]:
    rules = PORT_RULES.get(node.get("type"), {})
    lines = []
    for label, key in [("输入", "in"), ("输出", "out")]:
        ports = rules.get(key, [])
        if ports:
            names = " / ".join(PORT_LABELS.get(port, port) for port in ports)
            lines.append(f"{label}: {names}")
    return lines


def card_ports_by_direction(node: dict[str, Any]) -> list[tuple[str, list[str]]]:
    rules = PORT_RULES.get(node.get("type"), {})
    result = []
    for label, key in [("输入", "in"), ("输出", "out")]:
        ports = rules.get(key, [])
        if ports:
            result.append((label, [PORT_LABELS.get(port, port) for port in ports]))
    return result


def compact_text(text: str, max_chars: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def add_wrapped_text(parent: QGraphicsItem, text: str, x: float, y: float, width: float, color: str, font_size: int = 9, bold: bool = False) -> QGraphicsTextItem:
    item = QGraphicsTextItem(compact_text(text, 180), parent)
    item.setDefaultTextColor(QColor(color))
    weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
    item.setFont(QFont("Sans", font_size, weight if bold else -1))
    item.setTextWidth(width)
    item.setPos(x, y)
    return item


class PortItem(QGraphicsRectItem):
    SIZE = 13

    def __init__(self, node_item: "GraphNodeItem", direction: str, port_type: str, index: int):
        super().__init__(0, 0, self.SIZE, self.SIZE, node_item)
        self.node_item = node_item
        self.direction = direction
        self.port_type = port_type
        base = QColor(PORT_COLORS.get(port_type, "#90a4ae"))
        self.setBrush(QBrush(base.lighter(115) if direction == "out" else base.darker(115)))
        self.setPen(QPen(QColor("#eef4ff"), 1.2))
        y = node_item.port_start_y + index * 22
        x = node_item.WIDTH - self.SIZE - 8 if direction == "out" else 8
        self.setPos(x, y)
        if port_type in {"topic", "event", "state_machine", "transition_from", "transition_to"}:
            self.setRotation(45)
        elif port_type in {"module_input", "module_output", "group", "code"}:
            self.setScale(1.15)
        self.setToolTip(node_item.editor.port_detail_tooltip(node_item.node, direction, port_type))
        self.setZValue(2)

    def mousePressEvent(self, event):
        self.node_item.editor.begin_port_drag(self)
        event.accept()

    def mouseMoveEvent(self, event):
        self.node_item.editor.update_port_drag(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.node_item.editor.finish_port_drag(event.scenePos(), self)
        event.accept()


def node_theme(node_type: str) -> dict[str, str]:
    """Return accent/bg/border colors for a given node type."""
    accent = PORT_COLORS.get("hal", "#26c6da")
    for group, color in [
        ("hal.", "#26c6da"), ("sensor.", "#66bb6a"), ("processor.", "#29b6f6"),
        ("algorithm.", "#ab47bc"), ("actuator.", "#ec407a"), ("module.", "#ffb300"),
        ("event.", "#ef5350"), ("task.", "#5c6bc0"), ("state.", "#00acc1"),
        ("project.", "#ffffff"), ("data.", "#90a4ae"), ("custom.", "#78909c"),
    ]:
        if node_type.startswith(group):
            accent = color
            break
    return {"accent": accent, "bg": "#182033", "border": "#2f3a52"}


class GraphNodeItem(QGraphicsRectItem):
    WIDTH = 170
    HEIGHT = 70

    def __init__(self, node: dict[str, Any], editor: "VisualEditorWindow"):
        summary_text = node_summary(node)
        title_text = card_display_name(node)
        node_id = str(node.get("id", "node"))
        label_text = TYPE_LABELS.get(node.get("type"), node.get("type", "unknown"))
        desc_text = card_description(node)
        port_groups = card_ports_by_direction(node)
        # Use actual font metrics for width (handles CJK correctly, not char*6px)
        fm = QFontMetrics(QFont("Sans", 11))
        text_w = max(fm.horizontalAdvance(str(title_text)) if hasattr(fm, "horizontalAdvance") else fm.width(str(title_text)),
                     fm.horizontalAdvance(str(label_text)) if hasattr(fm, "horizontalAdvance") else fm.width(str(label_text)),
                     (fm.horizontalAdvance(str(summary_text)) if hasattr(fm, "horizontalAdvance") else fm.width(str(summary_text))) if summary_text else 0)
        self.WIDTH = max(250, min(390, int(text_w) + 100))
        port_count = max(len(PORT_RULES.get(node.get("type"), {}).get("in", [])), len(PORT_RULES.get(node.get("type"), {}).get("out", [])))
        desc_height = 34 if desc_text else 0
        summary_height = 28 if summary_text else 0
        port_text_height = 26 * sum(len(ports) for _, ports in port_groups)
        # Reduce base height when no description — avoid 34px of wasted empty space
        base_y = 126 if desc_text else 92
        self.port_start_y = base_y + summary_height + desc_height + port_text_height
        self.HEIGHT = max(self.port_start_y + max(port_count, 1) * 22 + 16, 168)
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.node = node
        self.editor = editor
        try:
            flags = (
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
        except AttributeError:
            flags = (
                QGraphicsItem.ItemIsMovable
                | QGraphicsItem.ItemIsSelectable
                | QGraphicsItem.ItemSendsGeometryChanges
            )
        self.setFlags(flags)
        theme = node_theme(node.get("type"))
        self.setBrush(QBrush(QColor(theme["bg"])))
        border_color = "#e53935" if node.get("type") == "state.transition" and not str(node.get("condition", "")).strip() else theme["border"]
        self.setPen(QPen(QColor(border_color), 2 if border_color == "#e53935" else 1.4))
        shadow = QGraphicsRectItem(5, 6, self.WIDTH, self.HEIGHT, self)
        shadow.setBrush(QBrush(QColor(0, 0, 0, 55)))
        shadow.setPen(QPen(QColor(0, 0, 0, 0), 0))
        shadow.setZValue(-1)
        accent = QGraphicsRectItem(0, 0, 6, self.HEIGHT, self)
        accent.setBrush(QBrush(QColor(theme["accent"])))
        accent.setPen(QPen(QColor(theme["accent"]), 0))
        title = QGraphicsSimpleTextItem(str(title_text), self)
        title.setBrush(QBrush(QColor("#f8fbff")))
        bold_weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
        title.setFont(QFont("Sans", 11, bold_weight))
        title_rect = title.boundingRect()
        title.setPos(max(14, (self.WIDTH - title_rect.width()) / 2), 12)
        subtitle = QGraphicsSimpleTextItem(label_text, self)
        subtitle.setBrush(QBrush(QColor("#b9c6d8")))
        subtitle_rect = subtitle.boundingRect()
        subtitle.setPos(max(14, (self.WIDTH - subtitle_rect.width()) / 2), 36)
        id_item = QGraphicsSimpleTextItem(f"ID  {node_id}", self)
        id_item.setBrush(QBrush(QColor("#7f8da5")))
        id_item.setFont(QFont("Sans", 8))
        id_rect = id_item.boundingRect()
        id_item.setPos(max(14, (self.WIDTH - id_rect.width()) / 2), 58)
        y_cursor = 82
        if summary_text:
            add_wrapped_text(self, "摘要：" + summary_text, 18, y_cursor, self.WIDTH - 36, "#aab7cc", 8)
            y_cursor += 28
        if desc_text:
            add_wrapped_text(self, "说明：" + desc_text, 18, y_cursor, self.WIDTH - 36, "#8f9db2", 8)
            y_cursor += 34
        if port_groups:
            heading = QGraphicsSimpleTextItem("接口", self)
            heading.setBrush(QBrush(QColor("#dce7ff")))
            heading.setFont(QFont("Sans", 8, bold_weight))
            heading.setPos(18, y_cursor + 2)
            y_cursor += 22
            for direction, ports in port_groups:
                for port_name in ports:
                    chip = QGraphicsRectItem(18, y_cursor, self.WIDTH - 36, 18, self)
                    chip.setBrush(QBrush(QColor("#182033")))
                    chip.setPen(QPen(QColor("#2f3a52"), 1))
                    chip_text = QGraphicsSimpleTextItem(f"{direction}  {port_name}", self)
                    chip_text.setBrush(QBrush(QColor("#c7d4e8")))
                    chip_text.setFont(QFont("Sans", 8))
                    chip_text.setPos(28, y_cursor + 1)
                    y_cursor += 24
        separator = QGraphicsRectItem(14, self.port_start_y - 6, self.WIDTH - 28, 1, self)
        separator.setBrush(QBrush(QColor("#30394b")))
        separator.setPen(QPen(QColor("#30394b"), 0))
        self.ports: list[PortItem] = []
        rules = PORT_RULES.get(node.get("type"), {})
        for idx, port_type in enumerate(rules.get("in", [])):
            self.ports.append(PortItem(self, "in", port_type, idx))
        for idx, port_type in enumerate(rules.get("out", [])):
            self.ports.append(PortItem(self, "out", port_type, idx))

    def itemChange(self, change, value):
        try:
            position_changed = QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        except AttributeError:
            position_changed = QGraphicsItem.ItemPositionHasChanged
        if change == position_changed:
            self.editor.update_node_position(self.node.get("id"), value)
            # Throttle edge refresh to ~20fps during drag (avoid O(n) per-pixel rebuild)
            import time
            now = time.monotonic()
            last = getattr(self.editor, "_last_edge_refresh", 0.0)
            if now - last >= 0.05:
                self.editor._last_edge_refresh = now
                self.editor.refresh_edges()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.editor.select_node(self.node.get("id"))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        page = page_for_node(self.node)
        if page:
            self.editor.open_page(page)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TemplatePalette(QListWidget):
    def __init__(self, editor: "VisualEditorWindow"):
        super().__init__()
        self.editor = editor
        self.setDragEnabled(True)

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if not item:
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        template_key = item.data(role)
        if template_key not in NODE_TEMPLATES:
            return
        mime = QMimeData()
        mime.setText(f"efw-template:{template_key}")
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class BlueprintView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, editor: "VisualEditorWindow"):
        super().__init__(scene)
        self.editor = editor
        self.setAcceptDrops(True)
        self.zoom_level = 1.0

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        if modifiers & ctrl:
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else event.delta()
            self.editor.zoom_relation_view(1.12 if delta > 0 else 1 / 1.12)
            event.accept()
            return
        super().wheelEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().text().startswith("efw-template:"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().text().startswith("efw-template:"):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("efw-template:"):
            template_key = text.split(":", 1)[1]
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.editor.add_card_from_template(template_key, self.mapToScene(pos))
            event.acceptProposedAction()
            return
        super().dropEvent(event)

