#!/usr/bin/env python3
"""Canvas rendering items and helpers for the EFW visual editor."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

import importlib.util

from studio.qt_compat import (
    Qt, QTimer, QRectF, QPointF, QSizeF, QMimeData,
    QBrush, QColor, QFont, QFontMetrics, QPen, QPainter, QPainterPath, QPixmap, QIcon,
    QGraphicsDropShadowEffect, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
    QGraphicsObject, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QGraphicsTextItem, QGraphicsView,
    QLineEdit, QListWidget, QMenu, QPushButton, QWidget,
)

from codegen.graph import NODE_CONTRACTS, PORT_COLORS, PORT_LABELS, PORT_RULES
from studio.core import page_for_node
from studio.editor_registry import NODE_TEMPLATES, TYPE_LABELS

if TYPE_CHECKING:
    from studio.editor import VisualEditorWindow


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
    return str(node.get("display_name") or node.get("title") or node.get("id") or "未命名")


def card_description(node: dict[str, Any]) -> str:
    return str(node.get("description") or node.get("note") or NODE_CONTRACTS.get(str(node.get("type")), {}).get("boundary", ""))


def compact_text(text: str, max_chars: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


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


def add_wrapped_text(parent: QGraphicsItem, text: str, x: float, y: float, width: float, color: str, font_size: int = 9, bold: bool = False) -> QGraphicsTextItem:
    item = QGraphicsTextItem(compact_text(text, 180), parent)
    item.setDefaultTextColor(QColor(color))
    weight = QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold
    item.setFont(QFont("Sans", font_size, weight if bold else -1))
    item.setTextWidth(width)
    item.setPos(x, y)
    return item


class PortItem(QGraphicsEllipseItem):
    SIZE = 12

    def __init__(self, node_item: "GraphNodeItem", direction: str, port_type: str, label: str):
        super().__init__(-self.SIZE / 2, -self.SIZE / 2, self.SIZE, self.SIZE, node_item)
        self.node_item = node_item
        self.direction = direction
        self.port_type = port_type
        self.label = label
        self.base_color = QColor(PORT_COLORS.get(port_type, "#26c6da"))
        self.is_enabled = True
        self.preview_state = "normal"
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._update_style(False)

    def _update_style(self, hovered: bool = False) -> None:
        if not self.is_enabled:
            self.setBrush(QBrush(QColor("#5a6478")))
            self.setPen(QPen(QColor("#111624"), 3.0))
            return
        if self.preview_state == "dim":
            fill_color = QColor("#4b5568")
        elif self.preview_state == "highlight":
            fill_color = self.base_color.lighter(155 if hovered else 145)
        else:
            fill_color = self.base_color.lighter(130) if hovered else self.base_color
        self.setBrush(QBrush(fill_color))
        stroke_color = QColor("#26c6da") if hovered or self.preview_state == "highlight" else QColor("#111624")
        stroke_width = 2.5 if hovered else 3.0
        self.setPen(QPen(stroke_color, stroke_width))

    def set_enabled_state(self, enabled: bool) -> None:
        self.is_enabled = enabled
        self._update_style(False)

    def set_preview_state(self, state: str) -> None:
        self.preview_state = state
        self._update_style(state == "highlight")

    def mousePressEvent(self, event):
        if not self.is_enabled:
            event.ignore()
            return
        self.node_item.editor.begin_port_drag(self)
        event.accept()

    def mouseMoveEvent(self, event):
        self.node_item.editor.update_port_drag(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.node_item.editor.finish_port_drag(event.scenePos(), self)
        event.accept()

    def hoverEnterEvent(self, event):
        if not self.is_enabled:
            self.setCursor(Qt.CursorShape.ForbiddenCursor if hasattr(Qt, "CursorShape") else Qt.ForbiddenCursor)
            return
        self.setCursor(Qt.CursorShape.CrossCursor if hasattr(Qt, "CursorShape") else Qt.CrossCursor)
        self.setScale(1.3)
        self._update_style(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor if hasattr(Qt, "CursorShape") else Qt.ArrowCursor)
        self.setScale(1.0)
        self._update_style(False)
        super().hoverLeaveEvent(event)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, edge: dict[str, Any], editor: "VisualEditorWindow"):
        super().__init__()
        self.edge = edge
        self.editor = editor
        self._dash_offset = 0.0
        self.setZValue(-1)
        self.refresh_pen()

    def refresh_pen(self):
        selected = str(self.edge.get("id")) == getattr(self.editor, "selected_edge_id", None)
        pen = self.editor.edge_pen_for_item(self.edge, selected=selected, dash_offset=self._dash_offset)
        self.setPen(pen)

    def advance_flow(self, amount: float = 1.0):
        self._dash_offset -= amount
        self.refresh_pen()

    def set_emphasis_pen(self, pen: QPen):
        self.setPen(pen)

    def update_path(self, start_pos: QPointF, end_pos: QPointF, start_dir: str = "right", end_dir: str = "left"):
        """Update edge path with UE5-style bezier curve.
        
        Args:
            start_pos: Starting position (source port)
            end_pos: Ending position (target port)
            start_dir: Direction the start port faces ("left" or "right")
            end_dir: Direction the end port faces ("left" or "right")
        """
        path = QPainterPath(start_pos)
        
        # Calculate horizontal distance
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        # Minimum control point distance
        min_ctrl_dist = 60.0
        
        # Scale factor based on distance
        if abs_dx > 200:
            ctrl_dist = abs_dx * 0.4
        elif abs_dx > 100:
            ctrl_dist = abs_dx * 0.5
        else:
            ctrl_dist = max(abs_dx * 0.6, min_ctrl_dist)
        
        # For backwards connections, use larger control distance
        if dx < 0:
            ctrl_dist = max(ctrl_dist, abs_dy * 0.5 + 100)
        
        # Calculate control points based on port direction
        # Output ports face right, input ports face left (normal case)
        # When flipped, output ports face left, input ports face right
        if start_dir == "right":
            ctrl1 = QPointF(start_pos.x() + ctrl_dist, start_pos.y())
        else:  # left
            ctrl1 = QPointF(start_pos.x() - ctrl_dist, start_pos.y())
        
        if end_dir == "left":
            ctrl2 = QPointF(end_pos.x() - ctrl_dist, end_pos.y())
        else:  # right
            ctrl2 = QPointF(end_pos.x() + ctrl_dist, end_pos.y())
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)

    def mousePressEvent(self, event):
        self.editor.select_edge(self.edge)
        event.accept()


class BackdropItem(QGraphicsRectItem):
    def __init__(self, group: dict[str, Any], editor: "VisualEditorWindow"):
        super().__init__()
        self.group = group
        self.editor = editor
        self.setZValue(-20)
        self._drag_origin = None
        self._member_origin_positions: dict[str, list[float]] = {}
        self.title_item = QGraphicsSimpleTextItem(str(group.get("title", "分组区域")), self)
        self.title_item.setBrush(QBrush(QColor("#9ddcff")))
        self.title_item.setFont(QFont("Sans", 11, QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold))
        self.title_item.setPos(12, 10)
        try:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        except AttributeError:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def group_rect(self) -> QRectF:
        raw = self.group.get("rect", [-180, -140, 420, 260])
        if not isinstance(raw, list) or len(raw) != 4:
            raw = [-180, -140, 420, 260]
        return QRectF(float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))

    def update_geometry(self):
        rect = self.group_rect()
        self.setRect(rect)
        self.title_item.setPos(rect.x() + 12, rect.y() + 10)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing)
        rect = self.rect()
        border = QColor("#26C6DA") if self.isSelected() else QColor(255, 255, 255, 45)
        fill = QColor(255, 255, 255, 12 if self.isSelected() else 8)
        painter.setBrush(QBrush(fill))
        pen = QPen(border, 1.2)
        pen.setStyle(Qt.PenStyle.DashLine if hasattr(Qt, "PenStyle") else Qt.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 12.0, 12.0)

    def mousePressEvent(self, event):
        self._drag_origin = event.scenePos()
        self._member_origin_positions = {
            str(node_id): list(self.editor.page_positions().get(str(node_id), [0.0, 0.0]))
            for node_id in self.group.get("node_ids", [])
        }
        self.editor.select_backdrop(self.group)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            delta = event.scenePos() - self._drag_origin
            for node_id, origin in self._member_origin_positions.items():
                self.editor.page_positions()[node_id] = [round(origin[0] + delta.x(), 1), round(origin[1] + delta.y(), 1)]
            rect = self.group_rect()
            self.group["rect"] = [round(rect.x() + delta.x(), 1), round(rect.y() + delta.y(), 1), round(rect.width(), 1), round(rect.height(), 1)]
            self.editor.refresh_scene()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        self._member_origin_positions = {}
        super().mouseReleaseEvent(event)




class EventFlowIndicator(QGraphicsPathItem):
    """Visual indicator for event flow between nodes."""
    
    def __init__(self, source_pos: QPointF, target_pos: QPointF, 
                 topic_name: str, event_type: str = "publish"):
        super().__init__()
        self.topic_name = topic_name
        self.event_type = event_type
        self._dash_offset = 0.0
        
        # Set style
        color = QColor("#ff7043") if event_type == "publish" else QColor("#ff9800")
        pen = QPen(color, 2.5)
        pen.setStyle(Qt.PenStyle.DashDotLine if hasattr(Qt, "PenStyle") else Qt.DashDotLine)
        pen.setDashPattern([8, 4, 2, 4])
        self.setPen(pen)
        self.setZValue(5)
        
        # Create path
        self.update_path(source_pos, target_pos)
        
        # Add label
        self.label = QGraphicsSimpleTextItem(topic_name, self)
        self.label.setBrush(QBrush(color))
        self.label.setFont(QFont("Sans", 8))
        mid_x = (source_pos.x() + target_pos.x()) / 2
        mid_y = (source_pos.y() + target_pos.y()) / 2
        self.label.setPos(mid_x, mid_y - 15)
    
    def update_path(self, start: QPointF, end: QPointF):
        path = QPainterPath(start)
        
        # Create curved path
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        # Control points for curve
        ctrl1 = QPointF(start.x() + dx * 0.3, start.y())
        ctrl2 = QPointF(end.x() - dx * 0.3, end.y())
        
        path.cubicTo(ctrl1, ctrl2, end)
        
        # Add arrowhead
        arrow_size = 8
        angle = 3.14159 * 0.8  # Angle for arrowhead
        p1 = QPointF(end.x() - arrow_size * 0.7, end.y() - arrow_size * 0.5)
        p2 = QPointF(end.x() - arrow_size * 0.7, end.y() + arrow_size * 0.5)
        
        path.moveTo(end)
        path.lineTo(p1)
        path.moveTo(end)
        path.lineTo(p2)
        
        self.setPath(path)
    
    def advance_animation(self, amount: float = 1.0):
        self._dash_offset -= amount
        pen = self.pen()
        pen.setDashOffset(self._dash_offset)
        self.setPen(pen)


def node_theme(node_type: str) -> dict[str, str]:
    accent = PORT_COLORS.get("hal", "#26c6da")
    for group, color in [
        ("hal.", "#26c6da"),
        ("sensor.", "#66bb6a"),
        ("processor.", "#29b6f6"),
        ("algorithm.", "#ab47bc"),
        ("actuator.", "#ec407a"),
        ("module.", "#ffb300"),
        ("event.", "#ef5350"),
        ("task.", "#5c6bc0"),
        ("state.", "#00acc1"),
        ("project.", "#8ab4ff"),
        ("data.", "#90a4ae"),
        ("custom.", "#78909c"),
    ]:
        if node_type.startswith(group):
            accent = color
            break
    return {"accent": accent, "bg": "#182033", "border": "#2f3a52"}


class GraphNodeItem(QGraphicsObject):
    MIN_WIDTH = 180
    HEADER_HEIGHT = 36
    PORT_ROW_HEIGHT = 26
    BODY_TOP_PADDING = 12
    BODY_BOTTOM_PADDING = 16

    def __init__(self, node: dict[str, Any], editor: "VisualEditorWindow"):
        super().__init__()
        self.node = node
        self.editor = editor
        self.is_hovered = False
        self._press_scene_pos: QPointF | None = None
        self._dragged_during_press = False
        self._original_scene_pos: QPointF | None = None
        self.theme = node_theme(node.get("type"))
        self._current_lod = 1.0
        self.title_text = str(card_display_name(node))
        self.type_text = str(node.get("type", "unknown")).split(".")[-1].upper()
        rules = PORT_RULES.get(node.get("type"), {})
        self.in_ports = list(rules.get("in", []))
        self.out_ports = list(rules.get("out", []))
        title_metrics = QFontMetrics(QFont("Segoe UI", 10))
        port_metrics = QFontMetrics(QFont("Segoe UI", 9))
        title_width = title_metrics.horizontalAdvance(self.title_text) if hasattr(title_metrics, "horizontalAdvance") else title_metrics.width(self.title_text)
        max_in_w = max([port_metrics.horizontalAdvance(PORT_LABELS.get(p, p)) if hasattr(port_metrics, "horizontalAdvance") else port_metrics.width(PORT_LABELS.get(p, p)) for p in self.in_ports] + [0])
        max_out_w = max([port_metrics.horizontalAdvance(PORT_LABELS.get(p, p)) if hasattr(port_metrics, "horizontalAdvance") else port_metrics.width(PORT_LABELS.get(p, p)) for p in self.out_ports] + [0])
        self.WIDTH = max(self.MIN_WIDTH, 24 + max_in_w + 30 + max_out_w + 24, title_width + 40)
        port_rows = max(len(self.in_ports), len(self.out_ports), 1)
        self.BODY_HEIGHT = max(40, port_rows * self.PORT_ROW_HEIGHT + self.BODY_BOTTOM_PADDING)
        self.HEIGHT = self.HEADER_HEIGHT + self.BODY_HEIGHT
        self.port_start_y = self.HEADER_HEIGHT + self.BODY_TOP_PADDING
        self._show_port_labels = True
        self._show_header_meta = True
        self.setAcceptHoverEvents(True)
        try:
            flags = (
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
        except AttributeError:
            flags = QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges
        self.setFlags(flags)
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setOffset(0, 8)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(self.shadow)
        self.setToolTip(self.editor.node_tooltip_text(self.node))
        self.ports: list[PortItem] = []
        for idx, port_type in enumerate(self.in_ports):
            y = self.HEADER_HEIGHT + self.BODY_TOP_PADDING + idx * self.PORT_ROW_HEIGHT + (self.PORT_ROW_HEIGHT / 2)
            port = PortItem(self, "in", port_type, port_type)
            port.setPos(0, y)
            port.setToolTip(self.editor.port_detail_tooltip(self.node, "in", port_type))
            self.ports.append(port)
        for idx, port_type in enumerate(self.out_ports):
            y = self.HEADER_HEIGHT + self.BODY_TOP_PADDING + idx * self.PORT_ROW_HEIGHT + (self.PORT_ROW_HEIGHT / 2)
            port = PortItem(self, "out", port_type, port_type)
            port.setPos(self.WIDTH, y)
            port.setToolTip(self.editor.port_detail_tooltip(self.node, "out", port_type))
            self.ports.append(port)
        for port in self.ports:
            port.set_enabled_state(self.editor.port_is_enabled(self.node, port.direction, port.port_type))
        self.update_lod(1.0)
        self._ports_flipped = False

    def flip_ports(self) -> None:
        """Manually flip input/output port positions."""
        self._ports_flipped = not self._ports_flipped
        self._reposition_ports()
        self.update()  # Trigger repaint to update labels

    def _reposition_ports(self) -> None:
        """Reposition ports based on flip state."""
        for port in self.ports:
            if port.direction == "in":
                if self._ports_flipped:
                    port.setPos(self.WIDTH, port.y())
                else:
                    port.setPos(0, port.y())
            else:  # out
                if self._ports_flipped:
                    port.setPos(0, port.y())
                else:
                    port.setPos(self.WIDTH, port.y())

    def boundingRect(self):
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter, option, widget=None):
        render_hint = QPainter.RenderHint if hasattr(QPainter, "RenderHint") else QPainter
        painter.setRenderHint(render_hint.Antialiasing)
        painter.setRenderHint(render_hint.TextAntialiasing)
        rect = self.boundingRect()
        radius = 8.0
        body_color = QColor("#111624") if not self.isSelected() else QColor("#1A2235")
        border_color = QColor(self.theme.get("border", "#2f3a52"))
        if self.node.get("type") == "state.transition" and not str(self.node.get("condition", "")).strip():
            border_color = QColor("#e53935")
        painter.setBrush(QBrush(body_color))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(rect, radius, radius)

        header_rect = QRectF(0, 0, self.WIDTH, self.HEADER_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
        header_color = QColor(self.theme["accent"])
        header_color.setAlpha(180 if self.isSelected() else 100)
        try:
            painter.setPen(Qt.PenStyle.NoPen)
        except AttributeError:
            painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(header_color))
        painter.drawRect(header_rect)
        painter.setClipping(False)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold if hasattr(QFont, "Weight") else QFont.Bold))
        painter.drawText(QRectF(14, 0, self.WIDTH - 28, self.HEADER_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignLeft), self.title_text)
        if self._show_header_meta:
            painter.setPen(QColor("#8F9DB2"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRectF(14, 0, self.WIDTH - 28, self.HEADER_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignRight), self.type_text)

        if self._show_port_labels:
            painter.setPen(QColor("#DCE7FF"))
            painter.setFont(QFont("Segoe UI", 9))
            for idx, port_type in enumerate(self.in_ports):
                label = PORT_LABELS.get(port_type, port_type)
                y = self.HEADER_HEIGHT + self.BODY_TOP_PADDING + idx * self.PORT_ROW_HEIGHT
                if self._ports_flipped:
                    # When flipped, input port is on right, label on right
                    painter.drawText(QRectF(self.WIDTH / 2, y, self.WIDTH / 2 - 16, self.PORT_ROW_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignRight), label)
                else:
                    # Normal: input port on left, label on left
                    painter.drawText(QRectF(16, y, self.WIDTH / 2, self.PORT_ROW_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignLeft), label)
            for idx, port_type in enumerate(self.out_ports):
                label = PORT_LABELS.get(port_type, port_type)
                y = self.HEADER_HEIGHT + self.BODY_TOP_PADDING + idx * self.PORT_ROW_HEIGHT
                if self._ports_flipped:
                    # When flipped, output port is on left, label on left
                    painter.drawText(QRectF(16, y, self.WIDTH / 2, self.PORT_ROW_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignLeft), label)
                else:
                    # Normal: output port on right, label on right
                    painter.drawText(QRectF(self.WIDTH / 2, y, self.WIDTH / 2 - 16, self.PORT_ROW_HEIGHT), (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight) if hasattr(Qt, "AlignmentFlag") else (Qt.AlignVCenter | Qt.AlignRight), label)

    def itemChange(self, change, value):
        try:
            position_changed = QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            selected_changed = QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged
            position_change = QGraphicsItem.GraphicsItemChange.ItemPositionChange
        except AttributeError:
            position_changed = QGraphicsItem.ItemPositionHasChanged
            selected_changed = QGraphicsItem.ItemSelectedHasChanged
            position_change = QGraphicsItem.ItemPositionChange
        if change == position_changed:
            self._dragged_during_press = True
            self.editor.update_node_position(self.node.get("id"), value)
            import time
            now = time.monotonic()
            last = getattr(self.editor, "_last_edge_refresh", 0.0)
            if now - last >= 0.05:
                self.editor._last_edge_refresh = now
                self.editor.refresh_edges()
        if change == selected_changed:
            self.update()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.setCursor(Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor)
        self.shadow.setBlurRadius(30)
        self.shadow.setOffset(0, 12)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor if hasattr(Qt, "CursorShape") else Qt.ArrowCursor)
        self.shadow.setBlurRadius(20)
        self.shadow.setOffset(0, 8)
        self.update()
        super().hoverLeaveEvent(event)

    def update_lod(self, lod: float) -> None:
        self._current_lod = lod
        show_ports = lod >= 0.4
        self._show_header_meta = lod >= 0.45
        self._show_port_labels = lod >= 0.55
        for port in self.ports:
            port.setVisible(show_ports)
        self.shadow.setEnabled(lod >= 0.55)

    def mousePressEvent(self, event):
        self._press_scene_pos = event.scenePos() if hasattr(event, "scenePos") else None
        self._dragged_during_press = False
        self._original_scene_pos = self.scenePos()
        modifiers = event.modifiers() if hasattr(event, "modifiers") else Qt.NoModifier
        ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        preserve_selection = []
        if self.isSelected() and not (modifiers & ctrl):
            preserve_selection = [
                node_id for node_id, item in self.editor.node_items.items()
                if item.isSelected()
            ]
        self.editor.select_edge(None)
        super().mousePressEvent(event)
        if len(preserve_selection) > 1:
            for node_id in preserve_selection:
                if node_id in self.editor.node_items:
                    self.editor.node_items[node_id].setSelected(True)
        self.editor.begin_batch_drag(str(self.node.get("id")))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        moved = self._dragged_during_press
        if self._press_scene_pos is not None and hasattr(event, "scenePos"):
            delta = event.scenePos() - self._press_scene_pos
            moved = moved or (abs(delta.x()) > 4 or abs(delta.y()) > 4)
        if self._original_scene_pos is not None:
            scene_delta = self.scenePos() - self._original_scene_pos
            moved = moved or (abs(scene_delta.x()) > 0.5 or abs(scene_delta.y()) > 0.5)
        if not moved:
            self.editor.select_node(self.node.get("id"))
        self.editor.finish_batch_drag()
        self._press_scene_pos = None
        self._dragged_during_press = False
        self._original_scene_pos = None

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
    MIN_ZOOM = 0.35
    MAX_ZOOM = 3.0

    def __init__(self, scene: QGraphicsScene, editor: "VisualEditorWindow"):
        super().__init__(scene)
        self.editor = editor
        self.setAcceptDrops(True)
        self.zoom_level = 1.0
        render_hint = QPainter.RenderHint if hasattr(QPainter, "RenderHint") else QPainter
        self.setRenderHint(render_hint.Antialiasing)
        self.setRenderHint(render_hint.TextAntialiasing)
        self.setRenderHint(render_hint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate if hasattr(QGraphicsView, "ViewportUpdateMode") else QGraphicsView.MinimalViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground if hasattr(QGraphicsView, "CacheModeFlag") else QGraphicsView.CacheBackground)
        selection_mode = Qt.ItemSelectionMode.ContainsItemBoundingRect if hasattr(Qt, "ItemSelectionMode") else Qt.ContainsItemBoundingRect
        self.setRubberBandSelectionMode(selection_mode)
        try:
            flags = QGraphicsView.OptimizationFlag.DontSavePainterState | QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        except AttributeError:
            flags = QGraphicsView.DontSavePainterState | QGraphicsView.DontAdjustForAntialiasing
        self.setOptimizationFlags(flags)
        policy = Qt.ScrollBarPolicy if hasattr(Qt, "ScrollBarPolicy") else Qt
        self.setHorizontalScrollBarPolicy(policy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(policy.ScrollBarAlwaysOff)
        self.setStyleSheet("border: none; background-color: #0A0F1C;")
        self._set_pan_drag_mode()

    def _set_pan_drag_mode(self) -> None:
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if hasattr(QGraphicsView, "DragMode") else QGraphicsView.ScrollHandDrag)

    def _set_rubber_band_drag_mode(self) -> None:
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag if hasattr(QGraphicsView, "DragMode") else QGraphicsView.RubberBandDrag)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        painter.fillRect(rect, QColor("#0A0F1C"))
        grid_size = 20
        dot_color = QColor(255, 255, 255, 15)
        painter.setPen(QPen(dot_color, 1.5))
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)
        points = []
        for x in range(left, int(rect.right()), grid_size):
            for y in range(top, int(rect.bottom()), grid_size):
                points.append(QPointF(x, y))
        if points:
            painter.drawPoints(points)

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        shift = Qt.KeyboardModifier.ShiftModifier if hasattr(Qt, "KeyboardModifier") else Qt.ShiftModifier
        if modifiers & ctrl:
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else event.delta()
            zoom_factor = 1.15 if delta > 0 else 1 / 1.15
            target_zoom = self.zoom_level * zoom_factor
            if target_zoom < self.MIN_ZOOM:
                zoom_factor = self.MIN_ZOOM / self.zoom_level
                target_zoom = self.MIN_ZOOM
            elif target_zoom > self.MAX_ZOOM:
                zoom_factor = self.MAX_ZOOM / self.zoom_level
                target_zoom = self.MAX_ZOOM
            if abs(target_zoom - self.zoom_level) < 1e-6:
                event.accept()
                return
            anchor = QGraphicsView.ViewportAnchor.AnchorUnderMouse if hasattr(QGraphicsView, "ViewportAnchor") else QGraphicsView.AnchorUnderMouse
            self.setTransformationAnchor(anchor)
            self.scale(zoom_factor, zoom_factor)
            self.zoom_level = target_zoom
            self.editor.update_canvas_lod(self.zoom_level)
            event.accept()
            return
        if modifiers & shift:
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else event.delta()
            step = int(delta / 2) if delta else 0
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - step)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self.itemAt(pos) is None:
            if self.scene() is not None:
                self.scene().clearSelection()
            self.editor.select_edge(None)
            self.editor.select_node(None)
            self.editor.open_quick_add_palette(self.mapToGlobal(pos), self.mapToScene(pos))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        button = event.button() if hasattr(event, "button") else None
        modifiers = event.modifiers() if hasattr(event, "modifiers") else Qt.NoModifier
        ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        left_button = Qt.MouseButton.LeftButton if hasattr(Qt, "MouseButton") else Qt.LeftButton
        rubber_band = button == left_button and bool(modifiers & ctrl)
        if rubber_band:
            self._set_rubber_band_drag_mode()
        else:
            self._set_pan_drag_mode()
        if self.itemAt(pos) is None and not rubber_band:
            if self.scene() is not None:
                self.scene().clearSelection()
            self.editor.select_edge(None)
            self.editor.select_node(None)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._set_pan_drag_mode()

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
