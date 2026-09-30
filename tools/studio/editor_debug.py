#!/usr/bin/env python3
"""Debug and runtime flow analysis mixin for Studio editor.

Provides graphical visualization of:
- Dataflow pipelines (flowchart style)
- State machines (state diagram)
- Scheduler timeline (Gantt chart)
- Event pub/sub topology (connection diagram)
- Initialization sequence (animated progress)
"""

from __future__ import annotations

import json
import math
from typing import Any

from studio.qt_compat import (
    Qt, QTimer, QRectF, QPointF,
    QColor, QFont, QPen, QBrush, QPainter, QPainterPath, QLinearGradient,
    QCheckBox, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from codegen.debug import (
    analyze_dataflows,
    analyze_events,
    analyze_init_order,
    analyze_line_followers,
    analyze_scheduler,
    analyze_state_machines,
)
from tools.api.graph import validate_graph_data


# ─── Color Palette ────────────────────────────────────────────────────────────

COLORS = {
    "bg": QColor("#0B101A"),
    "panel_bg": QColor("#111624"),
    "grid": QColor("#1A2235"),
    "text": QColor("#E2E8F0"),
    "text_dim": QColor("#8F9DB2"),
    "accent": QColor("#26C6DA"),
    "accent2": QColor("#7C4DFF"),
    "success": QColor("#4CAF50"),
    "warning": QColor("#FFC107"),
    "error": QColor("#F44336"),
    "info": QColor("#2196F3"),
    "purple": QColor("#CE93D8"),
    "orange": QColor("#FF9800"),
    "pink": QColor("#E91E63"),
    "teal": QColor("#00BCD4"),
}

NODE_COLORS = {
    "sensor": QColor("#45C36C"),
    "processor": QColor("#FF9800"),
    "algorithm": QColor("#7C4DFF"),
    "actuator": QColor("#F44336"),
    "module": QColor("#2196F3"),
    "event": QColor("#FFC107"),
    "state": QColor("#CE93D8"),
    "hal": QColor("#26C6DA"),
}


# ─── Graphical Widgets ────────────────────────────────────────────────────────

class FlowChartView(QGraphicsView):
    """Flowchart visualization for dataflow pipelines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(COLORS["bg"]))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, "ScrollBarPolicy") else Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, "ScrollBarPolicy") else Qt.ScrollBarAsNeeded)

    def draw_dataflows(self, ctx: dict[str, Any]) -> None:
        """Draw dataflow pipelines."""
        self.scene.clear()
        flows = analyze_dataflows(ctx)
        if not flows:
            self._draw_empty_message("无数据流管道")
            return

        y_offset = 20
        for flow in flows:
            self._draw_single_flow(flow, y_offset)
            y_offset += 120

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _draw_single_flow(self, flow: dict, y: int) -> None:
        """Draw a single dataflow pipeline."""
        nodes = flow["nodes"]
        period = flow["period_ms"]
        idx = flow["index"]

        # Draw pipeline header
        header = QGraphicsSimpleTextItem(f"管道 #{idx} (周期={period}ms)")
        header.setBrush(QBrush(COLORS["accent"]))
        header.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        header.setPos(20, y)
        self.scene.addItem(header)

        # Draw nodes
        node_width = 120
        node_height = 50
        spacing = 40
        x = 20

        for i, node in enumerate(nodes):
            node_type = node["type"]
            color = self._get_node_color(node_type)

            # Draw node box
            rect = QGraphicsRectItem(x, y + 30, node_width, node_height)
            rect.setBrush(QBrush(color.darker(150)))
            rect.setPen(QPen(color, 2))
            rect.setGraphicsEffect(None)
            self.scene.addItem(rect)

            # Draw node label
            label = QGraphicsSimpleTextItem(node["id"])
            label.setBrush(QBrush(COLORS["text"]))
            label.setFont(QFont("Microsoft YaHei", 9))
            label.setPos(x + 10, y + 35)
            self.scene.addItem(label)

            # Draw type label
            type_label = QGraphicsSimpleTextItem(self._short_type(node_type))
            type_label.setBrush(QBrush(COLORS["text_dim"]))
            type_label.setFont(QFont("Microsoft YaHei", 8))
            type_label.setPos(x + 10, y + 55)
            self.scene.addItem(type_label)

            # Draw arrow to next node
            if i < len(nodes) - 1:
                arrow_x = x + node_width
                arrow_y = y + 30 + node_height / 2
                self._draw_arrow(arrow_x, arrow_y, arrow_x + spacing, arrow_y)

            x += node_width + spacing

    def _draw_arrow(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Draw an arrow between two points."""
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(QPen(COLORS["accent"], 2))
        self.scene.addItem(line)

        # Draw arrowhead
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 10
        p1 = QPointF(x2 - arrow_size * math.cos(angle - 0.5), y2 - arrow_size * math.sin(angle - 0.5))
        p2 = QPointF(x2 - arrow_size * math.cos(angle + 0.5), y2 - arrow_size * math.sin(angle + 0.5))

        path = QPainterPath()
        path.moveTo(QPointF(x2, y2))
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()

        arrow = QGraphicsPathItem(path)
        arrow.setBrush(QBrush(COLORS["accent"]))
        arrow.setPen(QPen(COLORS["accent"]))
        self.scene.addItem(arrow)

    def _get_node_color(self, node_type: str) -> QColor:
        """Get color for node type."""
        for key, color in NODE_COLORS.items():
            if key in node_type:
                return color
        return COLORS["accent"]

    def _short_type(self, node_type: str) -> str:
        """Get short type label."""
        parts = node_type.split(".")
        return parts[-1] if len(parts) > 1 else node_type

    def _draw_empty_message(self, message: str) -> None:
        """Draw an empty state message."""
        text = QGraphicsSimpleTextItem(message)
        text.setBrush(QBrush(COLORS["text_dim"]))
        text.setFont(QFont("Microsoft YaHei", 12))
        text.setPos(50, 50)
        self.scene.addItem(text)


class StateMachineView(QGraphicsView):
    """State machine visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(COLORS["bg"]))

    def draw_state_machines(self, ctx: dict[str, Any]) -> None:
        """Draw state machines."""
        self.scene.clear()
        machines = analyze_state_machines(ctx)
        if not machines:
            self._draw_empty_message("无状态机")
            return

        x_offset = 20
        for machine in machines:
            self._draw_single_machine(machine, x_offset)
            x_offset += 300

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _draw_single_machine(self, machine: dict, x: int) -> None:
        """Draw a single state machine."""
        machine_id = machine["id"]
        states = machine["states"]
        transitions = machine["transitions"]
        initial = machine["initial"]

        # Draw machine header
        header = QGraphicsSimpleTextItem(f"状态机: {machine_id}")
        header.setBrush(QBrush(COLORS["purple"]))
        header.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        header.setPos(x, 20)
        self.scene.addItem(header)

        # Draw states in a circle layout
        state_radius = 30
        state_positions = {}
        num_states = len(states)
        if num_states == 0:
            return

        # Calculate positions in a circle
        center_x = x + 150
        center_y = 150
        radius = 100

        for i, state in enumerate(states):
            angle = 2 * math.pi * i / num_states - math.pi / 2
            sx = center_x + radius * math.cos(angle)
            sy = center_y + radius * math.sin(angle)
            state_positions[state["id"]] = (sx, sy)

            # Draw state circle
            is_initial = state["id"] == initial
            color = COLORS["accent"] if is_initial else COLORS["info"]

            circle = QGraphicsEllipseItem(sx - state_radius, sy - state_radius, state_radius * 2, state_radius * 2)
            circle.setBrush(QBrush(color.darker(200)))
            circle.setPen(QPen(color, 3 if is_initial else 2))
            self.scene.addItem(circle)

            # Draw state name
            label = QGraphicsSimpleTextItem(state["id"])
            label.setBrush(QBrush(COLORS["text"]))
            label.setFont(QFont("Microsoft YaHei", 9))
            label.setPos(sx - label.boundingRect().width() / 2, sy - 8)
            self.scene.addItem(label)

            # Draw initial indicator
            if is_initial:
                indicator = QGraphicsSimpleTextItem("初始")
                indicator.setBrush(QBrush(COLORS["warning"]))
                indicator.setFont(QFont("Microsoft YaHei", 7))
                indicator.setPos(sx - 10, sy + state_radius + 5)
                self.scene.addItem(indicator)

        # Draw transitions
        for trans in transitions:
            from_id = trans["from"]
            to_id = trans["to"]
            if from_id in state_positions and to_id in state_positions:
                self._draw_transition(state_positions[from_id], state_positions[to_id],
                                     state_radius, trans)

    def _draw_transition(self, from_pos: tuple, to_pos: tuple, radius: int, trans: dict) -> None:
        """Draw a transition arrow between states."""
        fx, fy = from_pos
        tx, ty = to_pos

        # Calculate direction
        dx = tx - fx
        dy = ty - fy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist == 0:
            return

        # Normalize
        nx = dx / dist
        ny = dy / dist

        # Start and end points (offset by radius)
        x1 = fx + nx * radius
        y1 = fy + ny * radius
        x2 = tx - nx * radius
        y2 = ty - ny * radius

        # Draw line
        line = QGraphicsLineItem(x1, y1, x2, y2)
        color = COLORS["warning"] if trans.get("timeout_ms") else COLORS["success"]
        line.setPen(QPen(color, 2))
        self.scene.addItem(line)

        # Draw arrowhead
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 8
        p1 = QPointF(x2 - arrow_size * math.cos(angle - 0.5), y2 - arrow_size * math.sin(angle - 0.5))
        p2 = QPointF(x2 - arrow_size * math.cos(angle + 0.5), y2 - arrow_size * math.sin(angle + 0.5))

        path = QPainterPath()
        path.moveTo(QPointF(x2, y2))
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()

        arrow = QGraphicsPathItem(path)
        arrow.setBrush(QBrush(color))
        arrow.setPen(QPen(color))
        self.scene.addItem(arrow)

        # Draw label
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        label_text = trans["condition"]
        if trans.get("timeout_ms"):
            label_text += f" ({trans['timeout_ms']}ms)"

        label = QGraphicsSimpleTextItem(label_text)
        label.setBrush(QBrush(COLORS["text_dim"]))
        label.setFont(QFont("Microsoft YaHei", 7))
        label.setPos(mid_x - 20, mid_y - 15)
        self.scene.addItem(label)

    def _draw_empty_message(self, message: str) -> None:
        """Draw an empty state message."""
        text = QGraphicsSimpleTextItem(message)
        text.setBrush(QBrush(COLORS["text_dim"]))
        text.setFont(QFont("Microsoft YaHei", 12))
        text.setPos(50, 50)
        self.scene.addItem(text)


class TimelineView(QGraphicsView):
    """Scheduler timeline visualization (Gantt chart style)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(COLORS["bg"]))

    def draw_scheduler(self, ctx: dict[str, Any]) -> None:
        """Draw scheduler timeline."""
        self.scene.clear()
        tasks = analyze_scheduler(ctx)
        if not tasks:
            self._draw_empty_message("无调度任务")
            return

        # Group tasks by period
        by_period: dict[int, list[dict]] = {}
        for task in tasks:
            period = task["period_ms"]
            by_period.setdefault(period, []).append(task)

        tick_ms = int(ctx["project"].get("tick_ms", 1))
        max_time = 100  # Show 100ms timeline

        # Draw timeline header
        self._draw_timeline_header(max_time)

        # Draw tasks
        y = 60
        for period in sorted(by_period.keys()):
            period_tasks = by_period[period]
            for task in period_tasks:
                self._draw_task_bar(task, y, period, max_time, tick_ms)
                y += 40

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _draw_timeline_header(self, max_time: int) -> None:
        """Draw timeline header with time markers."""
        # Draw time axis
        for t in range(0, max_time + 1, 10):
            x = 200 + t * 4
            line = QGraphicsLineItem(x, 40, x, 50)
            line.setPen(QPen(COLORS["text_dim"], 1))
            self.scene.addItem(line)

            label = QGraphicsSimpleTextItem(f"{t}ms")
            label.setBrush(QBrush(COLORS["text_dim"]))
            label.setFont(QFont("Microsoft YaHei", 7))
            label.setPos(x - 10, 30)
            self.scene.addItem(label)

        # Draw axis line
        axis = QGraphicsLineItem(200, 50, 200 + max_time * 4, 50)
        axis.setPen(QPen(COLORS["text"], 2))
        self.scene.addItem(axis)

    def _draw_task_bar(self, task: dict, y: int, period: int, max_time: int, tick_ms: int) -> None:
        """Draw a task bar in the timeline."""
        task_name = task["name"]
        task_type = task["type"]

        # Get color based on type
        color_map = {
            "dataflow": COLORS["accent"],
            "task": COLORS["info"],
            "state_machine": COLORS["purple"],
            "event": COLORS["warning"],
            "module": COLORS["success"],
        }
        color = color_map.get(task_type, COLORS["accent"])

        # Draw task name
        label = QGraphicsSimpleTextItem(f"{task_name} ({period}ms)")
        label.setBrush(QBrush(COLORS["text"]))
        label.setFont(QFont("Microsoft YaHei", 9))
        label.setPos(10, y + 5)
        self.scene.addItem(label)

        # Draw task execution bars
        bar_height = 20
        for t in range(0, max_time, period):
            x = 200 + t * 4
            width = min(period, max_time - t) * 4

            rect = QGraphicsRectItem(x, y, width, bar_height)
            gradient = QLinearGradient(x, y, x, y + bar_height)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, color.darker(150))
            rect.setBrush(QBrush(gradient))
            rect.setPen(QPen(color.darker(200), 1))
            self.scene.addItem(rect)

    def _draw_empty_message(self, message: str) -> None:
        """Draw an empty state message."""
        text = QGraphicsSimpleTextItem(message)
        text.setBrush(QBrush(COLORS["text_dim"]))
        text.setFont(QFont("Microsoft YaHei", 12))
        text.setPos(50, 50)
        self.scene.addItem(text)


class EventTopologyView(QGraphicsView):
    """Event pub/sub topology visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(COLORS["bg"]))

    def draw_events(self, ctx: dict[str, Any]) -> None:
        """Draw event topology."""
        self.scene.clear()
        events = analyze_events(ctx)

        if not events["topics"] and not events["publishers"] and not events["subscribers"]:
            self._draw_empty_message("无事件系统")
            return

        # Draw topics in center
        topics = events["topics"]
        publishers = events["publishers"]
        subscribers = events["subscribers"]

        # Layout: publishers on left, topics in center, subscribers on right
        topic_x = 300
        topic_y_start = 50

        # Draw topics
        topic_positions = {}
        for i, topic in enumerate(topics):
            y = topic_y_start + i * 80
            topic_positions[topic["id"]] = (topic_x, y)
            self._draw_topic(topic, topic_x, y)

        # Draw publishers
        pub_x = 100
        for i, pub in enumerate(publishers):
            y = 50 + i * 60
            self._draw_publisher(pub, pub_x, y, topic_positions)

        # Draw subscribers
        sub_x = 500
        for i, sub in enumerate(subscribers):
            y = 50 + i * 60
            self._draw_subscriber(sub, sub_x, y, topic_positions)

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _draw_topic(self, topic: dict, x: int, y: int) -> None:
        """Draw a topic node."""
        # Draw hexagon shape
        size = 30
        path = QPainterPath()
        for i in range(6):
            angle = 2 * math.pi * i / 6 - math.pi / 6
            px = x + size * math.cos(angle)
            py = y + size * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()

        hex_item = QGraphicsPathItem(path)
        hex_item.setBrush(QBrush(COLORS["warning"].darker(200)))
        hex_item.setPen(QPen(COLORS["warning"], 2))
        self.scene.addItem(hex_item)

        # Draw label
        label = QGraphicsSimpleTextItem(topic["id"])
        label.setBrush(QBrush(COLORS["text"]))
        label.setFont(QFont("Microsoft YaHei", 8))
        label.setPos(x - label.boundingRect().width() / 2, y - 8)
        self.scene.addItem(label)

        # Draw type info
        info = QGraphicsSimpleTextItem(f"id={topic['topic_id']}")
        info.setBrush(QBrush(COLORS["text_dim"]))
        info.setFont(QFont("Microsoft YaHei", 7))
        info.setPos(x - info.boundingRect().width() / 2, y + 25)
        self.scene.addItem(info)

    def _draw_publisher(self, pub: dict, x: int, y: int, topic_positions: dict) -> None:
        """Draw a publisher node."""
        # Draw box
        rect = QGraphicsRectItem(x - 50, y - 15, 100, 30)
        rect.setBrush(QBrush(COLORS["success"].darker(200)))
        rect.setPen(QPen(COLORS["success"], 2))
        self.scene.addItem(rect)

        # Draw label
        label = QGraphicsSimpleTextItem(pub["id"])
        label.setBrush(QBrush(COLORS["text"]))
        label.setFont(QFont("Microsoft YaHei", 8))
        label.setPos(x - label.boundingRect().width() / 2, y - 8)
        self.scene.addItem(label)

        # Draw connection to topic
        topic_id = pub["topic"]
        if topic_id in topic_positions:
            tx, ty = topic_positions[topic_id]
            line = QGraphicsLineItem(x + 50, y, tx - 30, ty)
            line.setPen(QPen(COLORS["success"], 2))
            self.scene.addItem(line)

    def _draw_subscriber(self, sub: dict, x: int, y: int, topic_positions: dict) -> None:
        """Draw a subscriber node."""
        # Draw box
        rect = QGraphicsRectItem(x - 50, y - 15, 100, 30)
        rect.setBrush(QBrush(COLORS["info"].darker(200)))
        rect.setPen(QPen(COLORS["info"], 2))
        self.scene.addItem(rect)

        # Draw label
        label = QGraphicsSimpleTextItem(sub["id"])
        label.setBrush(QBrush(COLORS["text"]))
        label.setFont(QFont("Microsoft YaHei", 8))
        label.setPos(x - label.boundingRect().width() / 2, y - 8)
        self.scene.addItem(label)

        # Draw connection from topic
        topic_id = sub["topic"]
        if topic_id in topic_positions:
            tx, ty = topic_positions[topic_id]
            line = QGraphicsLineItem(tx + 30, ty, x - 50, y)
            line.setPen(QPen(COLORS["info"], 2))
            self.scene.addItem(line)

    def _draw_empty_message(self, message: str) -> None:
        """Draw an empty state message."""
        text = QGraphicsSimpleTextItem(message)
        text.setBrush(QBrush(COLORS["text_dim"]))
        text.setFont(QFont("Microsoft YaHei", 12))
        text.setPos(50, 50)
        self.scene.addItem(text)


class InitSequenceView(QWidget):
    """Initialization sequence visualization with progress indicators."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.items = []
        self.current_step = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_next)

    def draw_init_sequence(self, ctx: dict[str, Any]) -> None:
        """Draw initialization sequence."""
        # Clear existing
        for item in self.items:
            item.deleteLater()
        self.items.clear()

        order = analyze_init_order(ctx)
        if not order:
            label = QLabel("无初始化序列")
            label.setStyleSheet("color: #8F9DB2;")
            self.layout.addWidget(label)
            self.items.append(label)
            return

        # Group by phase
        phases: dict[str, list[dict]] = {}
        for entry in order:
            phases.setdefault(entry["phase"], []).append(entry)

        # Create visual items
        phase_colors = {
            "HAL Registration": COLORS["accent"],
            "Sensor Registration": COLORS["success"],
            "Actuator Registration": COLORS["error"],
            "Algorithm Registration": COLORS["purple"],
            "Module Registration": COLORS["info"],
            "Project Module Registration": COLORS["teal"],
            "Event Subscription": COLORS["warning"],
            "State Machine Registration": COLORS["pink"],
        }

        for phase, entries in phases.items():
            color = phase_colors.get(phase, COLORS["accent"])

            # Phase header
            header = QLabel(f"▸ {phase}")
            header.setStyleSheet(f"""
                QLabel {{
                    color: {color.name()};
                    font-weight: bold;
                    font-size: 12px;
                    padding: 8px 4px 4px 4px;
                    border-left: 3px solid {color.name()};
                    margin-left: 10px;
                }}
            """)
            self.layout.addWidget(header)
            self.items.append(header)

            # Entries
            for entry in entries:
                entry_widget = QLabel(f"    ● {entry['id']}")
                entry_widget.setStyleSheet("""
                    QLabel {
                        color: #E2E8F0;
                        font-size: 11px;
                        padding: 4px 4px 4px 20px;
                    }
                """)
                if entry.get("detail"):
                    entry_widget.setToolTip(entry["detail"])
                self.layout.addWidget(entry_widget)
                self.items.append(entry_widget)

        self.layout.addStretch()

    def _animate_next(self) -> None:
        """Animate to next step."""
        if self.current_step < len(self.items):
            self.items[self.current_step].setStyleSheet(
                self.items[self.current_step].styleSheet() + "background-color: rgba(38, 198, 218, 0.2);"
            )
            self.current_step += 1
        else:
            self.animation_timer.stop()


# ─── Debug Panel ──────────────────────────────────────────────────────────────

class DebugMixin:
    """Mixin that provides debug and runtime flow analysis for the editor."""

    def _build_debug_panel(self) -> QWidget:
        """Build the debug panel widget."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        # Section selection
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("显示部分:"))

        self.debug_sections = {
            "info": QCheckBox("项目信息"),
            "init": QCheckBox("初始化顺序"),
            "dataflow": QCheckBox("数据流"),
            "scheduler": QCheckBox("调度器"),
            "state": QCheckBox("状态机"),
            "events": QCheckBox("事件系统"),
            "loop": QCheckBox("运行循环"),
            "linefollower": QCheckBox("循迹车"),
        }

        for name, checkbox in self.debug_sections.items():
            checkbox.setChecked(name in {"init", "dataflow", "loop"})
            selector_layout.addWidget(checkbox)

        refresh_btn = QPushButton("刷新分析")
        refresh_btn.clicked.connect(self.refresh_debug_analysis)
        selector_layout.addWidget(refresh_btn)
        selector_layout.addStretch()

        layout.addLayout(selector_layout)

        # Tab widget for different visualizations
        self.debug_tabs = QTabWidget()
        self.debug_tabs.setTabPosition(QTabWidget.TabPosition.North if hasattr(QTabWidget, "TabPosition") else QTabWidget.North)

        # Create visualization widgets
        self.init_view = InitSequenceView()
        self.dataflow_view = FlowChartView()
        self.scheduler_view = TimelineView()
        self.state_view = StateMachineView()
        self.event_view = EventTopologyView()

        # Add tabs
        self.debug_tabs.addTab(self.init_view, "初始化")
        self.debug_tabs.addTab(self.dataflow_view, "数据流")
        self.debug_tabs.addTab(self.scheduler_view, "调度器")
        self.debug_tabs.addTab(self.state_view, "状态机")
        self.debug_tabs.addTab(self.event_view, "事件系统")

        layout.addWidget(self.debug_tabs)

        # Status bar
        self.debug_status = QLabel("点击刷新分析查看运行流程")
        self.debug_status.setStyleSheet("color: #8F9DB2; padding: 4px;")
        layout.addWidget(self.debug_status)

        return panel

    def refresh_debug_analysis(self) -> None:
        """Refresh the debug analysis output."""
        # Initialize debug_sections if not exists
        if not hasattr(self, "debug_sections"):
            self.debug_sections = {
                "info": QCheckBox("项目信息"),
                "init": QCheckBox("初始化顺序"),
                "dataflow": QCheckBox("数据流"),
                "scheduler": QCheckBox("调度器"),
                "state": QCheckBox("状态机"),
                "events": QCheckBox("事件系统"),
                "loop": QCheckBox("运行循环"),
                "linefollower": QCheckBox("循迹车"),
            }
            for name, checkbox in self.debug_sections.items():
                checkbox.setChecked(name in {"init", "dataflow", "state", "events"})
        
        # Initialize views if not exists
        if not hasattr(self, "init_view"):
            self.init_view = InitSequenceView()
        if not hasattr(self, "dataflow_view"):
            self.dataflow_view = FlowChartView()
        if not hasattr(self, "scheduler_view"):
            self.scheduler_view = TimelineView()
        if not hasattr(self, "state_view"):
            self.state_view = StateMachineView()
        if not hasattr(self, "event_view"):
            self.event_view = EventTopologyView()
        
        try:
            ctx = self._build_debug_context()
        except Exception as exc:
            if hasattr(self, "debug_status"):
                self.debug_status.setText(f"错误: {exc}")
                self.debug_status.setStyleSheet("color: #F44336; padding: 4px;")
            return

        sections = [name for name, checkbox in self.debug_sections.items() if checkbox.isChecked()]
        
        if not sections:
            if hasattr(self, "debug_status"):
                self.debug_status.setText("请选择至少一个分析部分")
            return

        # Update each visualization
        if "init" in sections:
            self.init_view.draw_init_sequence(ctx)

        if "dataflow" in sections:
            self.dataflow_view.draw_dataflows(ctx)

        if "scheduler" in sections:
            self.scheduler_view.draw_scheduler(ctx)

        if "state" in sections:
            self.state_view.draw_state_machines(ctx)

        if "events" in sections:
            self.event_view.draw_events(ctx)

        # Count items
        node_count = len(ctx.get('nodes', []))
        df_count = len(ctx.get('runtime_dataflows', []))
        sm_count = len([n for n in ctx.get('nodes', []) if n.get('type') == 'state.machine'])
        ev_count = len([n for n in ctx.get('nodes', []) if n.get('type') == 'event.topic'])

        if hasattr(self, "debug_status"):
            self.debug_status.setText(
                f"分析完成: {node_count} 节点 | {df_count} 数据流 | {sm_count} 状态机 | {ev_count} 事件Topic"
            )
            self.debug_status.setStyleSheet("color: #4CAF50; padding: 4px;")

    def _build_debug_context(self) -> dict[str, Any]:
        """Build the context for debug analysis from current graph."""
        return validate_graph_data(self.graph)

    def toggle_debug_panel(self) -> None:
        """Toggle the debug panel visibility."""
        if hasattr(self, 'bottom_dock'):
            if self.bottom_dock.isVisible():
                # Switch to debug tab if already visible
                for i in range(self.bottom_tabs.count()):
                    if self.bottom_tabs.tabText(i) == "运行分析":
                        self.bottom_tabs.setCurrentIndex(i)
                        break
            else:
                # Show the dock and switch to debug tab
                self.bottom_dock.show()
                for i in range(self.bottom_tabs.count()):
                    if self.bottom_tabs.tabText(i) == "运行分析":
                        self.bottom_tabs.setCurrentIndex(i)
                        break
                # Auto-refresh analysis
                self.refresh_debug_analysis()
