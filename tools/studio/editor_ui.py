#!/usr/bin/env python3
"""UI construction mixin for the EFW visual editor.

Extracted from editor.py: all _build_* methods that construct the
workspace tabs, inspector panels, and navigation layout.
"""

from __future__ import annotations

from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QKeySequence, QShortcut
    from PyQt6.QtWidgets import (
        QCheckBox, QComboBox, QDockWidget, QFormLayout, QGraphicsScene, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QMainWindow, QPlainTextEdit, QPushButton, QSplitter, QTabBar, QTabWidget,
        QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QKeySequence
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDockWidget, QFormLayout, QGraphicsScene, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QMainWindow, QPlainTextEdit, QPushButton, QShortcut, QSplitter, QTabBar,
        QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QWidget = QTabWidget = QTableWidget = QDockWidget = QMainWindow = QMenu = object
    QT_LIB = "missing"

from studio.editor_canvas import (
    BlueprintView, TemplatePalette, node_theme,
)
from studio.core.templates import node_summary
from studio.editor_registry import NODE_CATEGORIES, NODE_TEMPLATES, display_label, TYPE_LABELS
from studio.model import BOARD_PROFILES, GENERATED_APPLICATION_TREE


class UIBuilderMixin:
    """Mixin that provides all _build_* methods for VisualEditorWindow."""

    def _build_ui(self) -> None:
        global_qss = """
        QWidget {
            background-color: #151B2B;
            color: #DCE7FF;
            font-family: "Segoe UI", "San Francisco", "Noto Sans", sans-serif;
        }
        QListWidget {
            background-color: #111624;
            border: 1px solid #242D40;
            border-radius: 6px;
            outline: none;
        }
        QListWidget::item {
            padding: 8px 12px;
            border-radius: 4px;
            margin: 2px 4px;
        }
        QListWidget::item:hover {
            background-color: #1E273A;
        }
        QListWidget::item:selected {
            background-color: #26C6DA;
            color: #0A0F1C;
            font-weight: bold;
        }
        QPushButton {
            background-color: #242D40;
            color: #FFFFFF;
            border: 1px solid #364259;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #2D374D;
            border-color: #4A5A7A;
        }
        QPushButton:pressed {
            background-color: #1E2536;
        }
        QLineEdit, QComboBox, QPlainTextEdit {
            background-color: #0B101A;
            border: 1px solid #242D40;
            border-radius: 4px;
            padding: 6px;
            color: #E2E8F0;
        }
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
            border: 1px solid #26C6DA;
        }
        QSplitter::handle {
            background-color: #151B2B;
            width: 4px;
        }
        QSplitter::handle:hover {
            background-color: #26C6DA;
        }
        QTabWidget::pane {
            border: 1px solid #242D40;
            background: #151B2B;
            border-radius: 4px;
        }
        QTabBar::tab {
            background: #111624;
            color: #8F9DB2;
            padding: 8px 16px;
            border: 1px solid #242D40;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #151B2B;
            color: #FFFFFF;
            border-top: 2px solid #26C6DA;
            font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
            background: #1A2235;
        }
        """
        self.setStyleSheet(global_qss)
        if not self.embedded:
            toolbar = QToolBar("项目工具栏")
            self.addToolBar(toolbar)
            toolbar.addAction("新建", self.new_graph)
            toolbar.addAction("项目向导", self.project_wizard)
            toolbar.addAction("打开", self.open_graph)
            toolbar.addAction("保存", self.save_graph)
            toolbar.addAction("另存为", self.save_graph_as)
            toolbar.addAction("撤销", self.undo)
            toolbar.addAction("重做", self.redo)
            toolbar.addAction("校验", self.validate_current_graph)
            toolbar.addAction("生成", self.generate_application)
            toolbar.addAction("分组区域", self.create_backdrop_from_selection)
            self.left_dock_action = toolbar.addAction("资源")
            self.right_dock_action = toolbar.addAction("属性")
            self.bottom_dock_action = toolbar.addAction("输出")
            toolbar.addAction("快捷键", self.show_shortcuts)

        self.setDockNestingEnabled(True)
        try:
            dock_opts = (
                QMainWindow.DockOption.AnimatedDocks
                | QMainWindow.DockOption.AllowNestedDocks
                | QMainWindow.DockOption.AllowTabbedDocks
            )
        except AttributeError:
            dock_opts = QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks
        self.setDockOptions(dock_opts)

        left = QWidget()
        left.setObjectName("NavRail")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        self.workflow_list = QListWidget()
        workflow_steps = [
            ("项目总览", "dashboard"),
            ("模块装配", "assembly"),
            ("关系视图", "relations"),
            ("代码补齐", "code"),
            ("生成发布", "release"),
        ]
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        for label, key in workflow_steps:
            item = QListWidgetItem(label, self.workflow_list)
            item.setData(role, key)
        self.workflow_list.itemClicked.connect(self.switch_workflow_item)
        left_layout.addWidget(self.workflow_list)
        self.workflow_hint = QLabel("当前项目：从总览进入，按模块装配组件，最后校验生成。")
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setStyleSheet("background: #151a24; border: 1px solid #242936; border-radius: 12px; padding: 10px; color: #b8c3d8;")
        left_layout.addWidget(self.workflow_hint)
        current_container_btn = QPushButton("进入选中对象")
        current_container_btn.clicked.connect(self.open_selected_container)
        left_layout.addWidget(current_container_btn)

        self.palette_label = QLabel("快速添加")
        left_layout.addWidget(self.palette_label)
        self.palette_search = QLineEdit()
        self.palette_search.setPlaceholderText("搜索模板…")
        self.palette_search.textChanged.connect(self.filter_palette)
        left_layout.addWidget(self.palette_search)
        self.palette = TemplatePalette(self)
        self.palette.itemDoubleClicked.connect(self._on_palette_double_click)
        self._palette_category_visibility: dict[str, bool] = {}
        for category, node_types in NODE_CATEGORIES:
            header = QListWidgetItem(f"▾ {category}", self.palette)
            header.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, "__category__")
            header.setData(Qt.ItemDataRole.UserRole + 1 if hasattr(Qt, "ItemDataRole") else Qt.UserRole + 1, category)
            header.setBackground(QBrush(QColor("#233544")))
            header.setForeground(QBrush(QColor("#ffecb3")))
            for node_type in node_types:
                template_type = NODE_TEMPLATES.get(node_type, {}).get("type", node_type)
                item = QListWidgetItem(f"  {display_label(node_type)}  ({template_type})", self.palette)
                item.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, node_type)
                item.setData(Qt.ItemDataRole.UserRole + 1 if hasattr(Qt, "ItemDataRole") else Qt.UserRole + 1, category)
                theme = node_theme(template_type)
                item.setBackground(QBrush(QColor(theme["bg"])))
                item.setForeground(QBrush(QColor("#f4fbff")))
        left_layout.addWidget(self.palette)
        add_btn = QPushButton("添加到当前页面")
        add_btn.clicked.connect(self.add_selected_card)
        left_layout.addWidget(add_btn)
        backdrop_btn = QPushButton("创建分组区域")
        backdrop_btn.clicked.connect(self.create_backdrop_from_selection)
        left_layout.addWidget(backdrop_btn)
        left_layout.addWidget(QLabel("提示：双击画布空白处或按 Tab，可在鼠标位置快速搜索并插入节点。"))

        self.left_dock = QDockWidget("资源管理器", self)
        self.left_dock.setObjectName("LeftDock")
        try:
            features = (
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        except AttributeError:
            features = QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        self.left_dock.setFeatures(features)
        self.left_dock.setMinimumWidth(220)
        left.setMinimumWidth(220)
        self.left_dock.setWidget(left)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea if hasattr(Qt, "DockWidgetArea") else Qt.LeftDockWidgetArea, self.left_dock)

        self.center_tabs = QTabWidget()
        self.center_tabs.setMinimumWidth(360)
        self.center_tabs.setDocumentMode(True)
        self.center_tabs.setTabsClosable(False)
        self.center_tabs.addTab(self._build_dashboard_tab(), "🏠 项目总览")
        self.center_tabs.addTab(self._build_assembly_tab(), "📦 模块装配")

        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        self.page_tabs = QTabBar()
        self.page_tabs.setExpanding(False)
        self.page_tabs.setTabsClosable(True)
        self.page_tabs.currentChanged.connect(self.switch_page_tab)
        self.page_tabs.tabCloseRequested.connect(self.close_page_tab)
        canvas_layout.addWidget(self.page_tabs)
        page_controls = QHBoxLayout()
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.clicked.connect(lambda: self.zoom_relation_view(1 / 1.15))
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.clicked.connect(lambda: self.zoom_relation_view(1.15))
        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.clicked.connect(self.reset_relation_zoom)
        root_btn = QPushButton("返回根项目")
        root_btn.clicked.connect(self.exit_module)
        page_controls.addWidget(zoom_out_btn)
        page_controls.addWidget(zoom_in_btn)
        page_controls.addWidget(zoom_reset_btn)
        page_controls.addWidget(root_btn)
        canvas_layout.addLayout(page_controls)
        self.module_scope_label = QLabel("")
        canvas_layout.addWidget(self.module_scope_label)
        self.scene = QGraphicsScene()
        self.view = BlueprintView(self.scene, self)
        canvas_layout.addWidget(self.view)
        self.center_tabs.addTab(canvas, "🔵 关系视图")
        self.center_tabs.addTab(self._build_release_tab(), "🚀 生成发布")
        self.setCentralWidget(self.center_tabs)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        title_row = QHBoxLayout()
        inspector_title = QLabel("常用面板")
        inspector_title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #ffffff;")
        title_row.addWidget(inspector_title)
        self.advanced_toggle_btn = QPushButton("显示高级")
        self.advanced_toggle_btn.clicked.connect(self.toggle_advanced_panels)
        title_row.addWidget(self.advanced_toggle_btn)
        inspector_layout.addLayout(title_row)
        self.inspector_nav = QListWidget()
        inspector_layout.addWidget(self.inspector_nav)
        self.right_tabs = QTabWidget()
        self.right_tabs.setTabPosition(QTabWidget.TabPosition.South if hasattr(QTabWidget, "TabPosition") else QTabWidget.South)
        self.right_tabs.addTab(self._build_properties_tab(), "属性")
        self.right_tabs.addTab(self._build_code_tab(), "节点代码")
        self.right_tabs.addTab(self._build_pin_planner_tab(), "引脚配置")
        self.right_tabs.addTab(self._build_structure_tab(), "高级 · 项目结构")
        self.right_tabs.addTab(self._build_mapping_tab(), "高级 · 生成映射")
        self.right_tabs.addTab(self._build_file_tree_tab(), "高级 · 文件树预览")
        self.right_tabs.addTab(self._build_json_tab(), "高级 · Graph JSON")
        self._advanced_inspector_enabled = False
        self._advanced_tab_titles = {
            "高级 · 项目结构",
            "高级 · 生成映射",
            "高级 · 文件树预览",
            "高级 · Graph JSON",
        }
        self.inspector_nav.currentItemChanged.connect(self.switch_inspector_panel)
        self.rebuild_inspector_nav()
        self.right_tabs.tabBar().hide()
        inspector_layout.addWidget(self.right_tabs, 1)
        self.right_dock = QDockWidget("属性与详情", self)
        self.right_dock.setObjectName("RightDock")
        self.right_dock.setFeatures(features)
        self.right_dock.setMinimumWidth(300)
        inspector.setMinimumWidth(300)
        self.right_dock.setWidget(inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea if hasattr(Qt, "DockWidgetArea") else Qt.RightDockWidgetArea, self.right_dock)

        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.addTab(self._build_validation_tab(), "实时校验")
        self.bottom_tabs.addTab(self._build_release_tab(), "生成日志")
        self.bottom_tabs.addTab(self._build_schedule_tab(), "任务调度")
        self.bottom_tabs.setTabPosition(QTabWidget.TabPosition.South if hasattr(QTabWidget, "TabPosition") else QTabWidget.South)
        self.bottom_dock = QDockWidget("输出 / 日志", self)
        self.bottom_dock.setObjectName("BottomDock")
        self.bottom_dock.setFeatures(features)
        self.bottom_dock.setWidget(self.bottom_tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea if hasattr(Qt, "DockWidgetArea") else Qt.BottomDockWidgetArea, self.bottom_dock)
        self.bottom_dock.hide()
        if not self.embedded:
            self.left_dock_action.triggered.connect(self.toggle_left_dock)
            self.right_dock_action.triggered.connect(self.toggle_right_dock)
            self.bottom_dock_action.triggered.connect(self.toggle_bottom_dock)
            self.toggle_console_shortcut = QShortcut(QKeySequence("Ctrl+`"), self)
            self.toggle_console_shortcut.activated.connect(self.toggle_bottom_dock)
        self.resizeDocks([self.left_dock, self.right_dock], [260, 340], Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal)
        self._default_window_state = self.saveState()
        self.quick_add_shortcut = QShortcut(QKeySequence("Tab"), self)
        self.quick_add_shortcut.activated.connect(self.open_quick_add_palette_at_view_center)
        self._build_quick_add_popup()

    def _build_quick_add_popup(self) -> None:
        self.quick_add_popup = QWidget(self, Qt.WindowType.Popup if hasattr(Qt, "WindowType") else Qt.Popup)
        self.quick_add_popup.setStyleSheet("background: #111624; border: 1px solid #242D40; border-radius: 8px;")
        self.quick_add_popup.resize(320, 360)
        layout = QVBoxLayout(self.quick_add_popup)
        layout.setContentsMargins(8, 8, 8, 8)
        self.quick_add_input = QLineEdit()
        self.quick_add_input.setPlaceholderText("输入关键词，例如 motor / sensor / topic…")
        self.quick_add_input.textChanged.connect(self.filter_quick_add_palette)
        layout.addWidget(self.quick_add_input)
        self.quick_add_list = QListWidget()
        self.quick_add_list.itemDoubleClicked.connect(self.confirm_quick_add_palette)
        layout.addWidget(self.quick_add_list)
        self._quick_add_scene_pos = None
        self.filter_quick_add_palette("")

    def toggle_left_dock(self) -> None:
        if hasattr(self, "left_dock"):
            visible = not self.left_dock.isVisible()
            self.left_dock.setVisible(visible)
            if visible:
                self.left_dock.raise_()

    def toggle_right_dock(self) -> None:
        if hasattr(self, "right_dock"):
            visible = not self.right_dock.isVisible()
            self.right_dock.setVisible(visible)
            if visible:
                self.right_dock.raise_()

    def toggle_bottom_dock(self) -> None:
        if hasattr(self, "bottom_dock"):
            visible = not self.bottom_dock.isVisible()
            self.bottom_dock.setVisible(visible)
            if visible:
                self.bottom_dock.raise_()
                self.bottom_tabs.setCurrentIndex(0)
                self.resizeDocks([self.bottom_dock], [220], Qt.Orientation.Vertical if hasattr(Qt, "Orientation") else Qt.Vertical)
                if hasattr(self, "statusBar"):
                    self.statusBar().showMessage("已打开底部输出区：实时校验 / 生成日志 / 任务调度", 4000)

    def reset_dock_layout(self) -> None:
        if hasattr(self, "left_dock"):
            self.left_dock.setFloating(False)
        if hasattr(self, "right_dock"):
            self.right_dock.setFloating(False)
        if hasattr(self, "bottom_dock"):
            self.bottom_dock.setFloating(False)
        if hasattr(self, "_default_window_state"):
            self.restoreState(self._default_window_state)
        self.left_dock.show()
        self.right_dock.show()
        self.bottom_dock.hide()
        self.resizeDocks([self.left_dock, self.right_dock], [260, 340], Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal)

    def open_quick_add_palette_at_view_center(self) -> None:
        if not hasattr(self, "view"):
            return
        center = self.view.viewport().rect().center()
        global_pos = self.view.mapToGlobal(center)
        scene_pos = self.view.mapToScene(center)
        self.open_quick_add_palette(global_pos, scene_pos)

    def open_quick_add_palette(self, global_pos, scene_pos) -> None:
        self._quick_add_scene_pos = scene_pos
        self.filter_quick_add_palette("")
        self.quick_add_popup.move(global_pos)
        self.quick_add_popup.show()
        self.quick_add_input.setFocus()
        self.quick_add_input.selectAll()

    def filter_quick_add_palette(self, text: str) -> None:
        if not hasattr(self, "quick_add_list"):
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        self.quick_add_list.clear()
        keyword = text.strip().lower()
        for category, node_types in NODE_CATEGORIES:
            visible = []
            for node_type in node_types:
                label = f"{display_label(node_type)} {node_type}".lower()
                if keyword and keyword not in label:
                    continue
                visible.append(node_type)
            if not visible:
                continue
            header = QListWidgetItem(f"{category}", self.quick_add_list)
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsSelectable if hasattr(Qt, "ItemFlag") else header.flags())
            header.setData(role, "__category__")
            header.setForeground(QBrush(QColor("#7ec8ff")))
            for node_type in visible:
                item = QListWidgetItem(f"  {display_label(node_type)}", self.quick_add_list)
                item.setData(role, node_type)
        if self.quick_add_list.count() > 0:
            self.quick_add_list.setCurrentRow(1 if self.quick_add_list.count() > 1 else 0)

    def confirm_quick_add_palette(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.quick_add_list.currentItem()
        if not item:
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        node_type = item.data(role)
        if not node_type or node_type == "__category__":
            return
        self.quick_add_popup.hide()
        self.add_card_from_template(str(node_type), self._quick_add_scene_pos)

    def rebuild_inspector_nav(self) -> None:
        if not hasattr(self, "inspector_nav") or not hasattr(self, "right_tabs"):
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        current_index = self.right_tabs.currentIndex() if hasattr(self.right_tabs, "currentIndex") else 0
        self.inspector_nav.blockSignals(True)
        self.inspector_nav.clear()
        current_row = 0
        row = 0
        for index in range(self.right_tabs.count()):
            title = self.right_tabs.tabText(index)
            if not self._advanced_inspector_enabled and title in self._advanced_tab_titles:
                continue
            item = QListWidgetItem(title.replace("高级 · ", ""), self.inspector_nav)
            item.setData(role, index)
            if index == current_index:
                current_row = row
            row += 1
        if self.inspector_nav.count():
            self.inspector_nav.setCurrentRow(current_row)
        self.inspector_nav.blockSignals(False)

    def toggle_advanced_panels(self) -> None:
        self._advanced_inspector_enabled = not self._advanced_inspector_enabled
        self.advanced_toggle_btn.setText("隐藏高级" if self._advanced_inspector_enabled else "显示高级")
        if not self._advanced_inspector_enabled and self.right_tabs.tabText(self.right_tabs.currentIndex()) in self._advanced_tab_titles:
            self.right_tabs.setCurrentIndex(1)
        self.rebuild_inspector_nav()

    def switch_inspector_panel(self, current: QListWidgetItem, _previous: QListWidgetItem | None = None) -> None:
        if not current or not hasattr(self, "right_tabs"):
            return
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        index = current.data(role)
        if isinstance(index, int) and 0 <= index < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(index)

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("项目总览：先看项目状态，再进入模块装配或生成发布。"))
        self.dashboard_output = QPlainTextEdit()
        self.dashboard_output.setReadOnly(True)
        layout.addWidget(self.dashboard_output)
        buttons = QHBoxLayout()
        for text, callback in [
            ("进入模块装配", lambda: self.set_workspace("模块装配")),
            ("校验项目", self.validate_current_graph),
            ("生成发布", lambda: self.set_workspace("生成发布")),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return widget

    def _build_assembly_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("模块装配：以模块为单位组织 HAL / Sensor / Actuator / Algorithm / Task / Event / State。"))
        self.module_list = QListWidget()
        self.module_list.itemClicked.connect(self.open_module_item)
        layout.addWidget(self.module_list)
        buttons = QHBoxLayout()
        add_module_btn = QPushButton("新增模块")
        add_module_btn.clicked.connect(self.add_project_module)
        open_module_btn = QPushButton("进入模块")
        open_module_btn.clicked.connect(self.open_selected_module_from_list)
        relation_btn = QPushButton("查看关系")
        relation_btn.clicked.connect(lambda: self.set_workspace("关系视图"))
        buttons.addWidget(add_module_btn)
        buttons.addWidget(open_module_btn)
        buttons.addWidget(relation_btn)
        layout.addLayout(buttons)
        return widget

    def _build_release_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("生成发布：把校验、缺失回调、资源冲突和生成预览汇总成清单。"))
        self.release_output = QPlainTextEdit()
        self.release_output.setReadOnly(True)
        layout.addWidget(self.release_output)
        buttons = QHBoxLayout()
        validate_btn = QPushButton("刷新检查")
        validate_btn.clicked.connect(lambda: self.refresh_validation_panel(show_dialog=False))
        generate_btn = QPushButton("生成 application")
        generate_btn.clicked.connect(self.generate_application)
        buttons.addWidget(validate_btn)
        buttons.addWidget(generate_btn)
        layout.addLayout(buttons)
        return widget

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.selected_label = QLabel("未选择卡片")
        layout.addWidget(self.selected_label)
        self.ports_label = QLabel("端口：未选择")
        self.ports_label.setWordWrap(True)
        layout.addWidget(self.ports_label)
        self.property_table = QTableWidget(0, 4)
        self.property_table.setHorizontalHeaderLabels(["属性", "值", "控件类型", "契约"])
        self.property_table.setMinimumHeight(120)
        layout.addWidget(self.property_table)
        apply_form_btn = QPushButton("应用表单")
        apply_form_btn.clicked.connect(self.apply_property_form)
        layout.addWidget(apply_form_btn)
        layout.addWidget(QLabel("当前卡片回调实现："))
        callback_row = QHBoxLayout()
        self.callback_select = QComboBox()
        self.callback_select.currentTextChanged.connect(self.load_selected_callback_implementation)
        save_callback_btn = QPushButton("保存到 app_custom.c")
        save_callback_btn.clicked.connect(self.save_selected_callback_implementation)
        open_code_btn = QPushButton("打开代码页")
        open_code_btn.clicked.connect(lambda: self.set_right_tab("代码补齐"))
        callback_row.addWidget(self.callback_select)
        callback_row.addWidget(save_callback_btn)
        callback_row.addWidget(open_code_btn)
        layout.addLayout(callback_row)
        self.callback_preview_output = QPlainTextEdit()
        self.callback_preview_output.setMaximumHeight(180)
        self.callback_preview_output.setFont(QFont("Consolas", 9))
        layout.addWidget(self.callback_preview_output)
        layout.addWidget(QLabel("高级 JSON（复杂数组/对象可在这里编辑）"))
        self.node_json_editor = QPlainTextEdit()
        self.node_json_editor.setMaximumHeight(150)
        layout.addWidget(self.node_json_editor)
        apply_btn = QPushButton("应用 JSON")
        apply_btn.clicked.connect(self.apply_node_json)
        delete_btn = QPushButton("删除卡片")
        delete_btn.clicked.connect(self.delete_selected_node)
        layout.addWidget(apply_btn)
        layout.addWidget(delete_btn)
        return widget

    def _build_pin_planner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Board Profile 与 Pin Planner：只做资源规划和冲突检查，会写回 Graph/app_board_config.h；不会自动生成 STM32 HAL、ESP-IDF 或 DriverLib 调用。真实硬件代码请放入 board_adapters。"))
        self.board_profile_edit = QComboBox()
        self.board_profile_edit.addItems(list(BOARD_PROFILES))
        layout.addWidget(self.board_profile_edit)
        profile_btn = QPushButton("套用 Board Profile 默认资源")
        profile_btn.clicked.connect(self.apply_board_profile_defaults)
        layout.addWidget(profile_btn)
        edit_profile_btn = QPushButton("编辑 Board Profile…")
        edit_profile_btn.clicked.connect(self.edit_board_profile)
        layout.addWidget(edit_profile_btn)
        self.pin_table = QTableWidget(0, 5)
        self.pin_table.setHorizontalHeaderLabels(["节点", "用途", "端口/定时器", "引脚/通道", "备注"])
        layout.addWidget(self.pin_table)
        apply_btn = QPushButton("应用 Pin Planner")
        apply_btn.clicked.connect(self.apply_pin_planner)
        layout.addWidget(apply_btn)
        return widget

    def _build_validation_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("校验错误列表（点击可定位到相关卡片）："))
        self.validation_list = QListWidget()
        self.validation_list.itemClicked.connect(self.open_validation_item)
        layout.addWidget(self.validation_list)
        self.validation_output = QPlainTextEdit()
        self.validation_output.setReadOnly(True)
        layout.addWidget(self.validation_output)
        run_btn = QPushButton("立即校验")
        run_btn.clicked.connect(self.validate_current_graph)
        layout.addWidget(run_btn)
        return widget

    def _build_mapping_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.mapping_output = QPlainTextEdit()
        self.mapping_output.setReadOnly(True)
        layout.addWidget(self.mapping_output)
        return widget

    def _build_structure_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("项目结构：帮助你理解模块里已有的输入、处理、输出节点。"))
        self.structure_output = QPlainTextEdit()
        self.structure_output.setReadOnly(True)
        layout.addWidget(self.structure_output)
        return widget

    def _build_file_tree_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("高级视图：预览生成后的文件结构，确认自定义代码会落到哪里。"))
        self.file_tree_output = QPlainTextEdit()
        self.file_tree_output.setReadOnly(True)
        layout.addWidget(self.file_tree_output)
        return widget

    def _build_schedule_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("高级视图：查看运行调度预估，适合排查 task / flow / 状态机顺序。"))
        self.schedule_output = QPlainTextEdit()
        self.schedule_output.setReadOnly(True)
        layout.addWidget(self.schedule_output)
        return widget

    def shortcuts_text(self) -> str:
        return """快捷键
Ctrl+N    新建 Graph
Ctrl+O    打开 Graph
Ctrl+S    保存 Graph
Ctrl+Shift+S  另存为 Graph
Ctrl+Z    撤销
Ctrl+Y    重做
Ctrl+G    生成 application
Ctrl+M    添加当前选中的模板卡片
Ctrl+Shift+B 创建分组区域
Delete / Backspace 删除当前选中的对象（优先删连线）
Ctrl++ / Ctrl+- 关系视图缩放
Ctrl+0    关系视图恢复 100%
Ctrl+1..4 快速切换：总览 / 模块装配 / 关系视图 / 生成发布
Alt+1..4  快速切换 Inspector：项目结构 / 属性 / 代码 / 校验
F5        实时校验
Esc       返回根项目页面

当前阶段先固定快捷键，避免设置项和项目文件格式过早复杂化；如果后续用户频繁冲突，再加入可配置快捷键。"""

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "快捷键", self.shortcuts_text())

    def _build_code_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        header = QHBoxLayout()
        title = QLabel("Code Workspace")
        title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #ffffff;")
        self.code_status_label = QLabel("未选择文件")
        self.code_status_label.setStyleSheet("color: #8f9db2;")
        header.addWidget(title)
        header.addWidget(self.code_status_label)
        layout.addLayout(header)
        row = QHBoxLayout()
        self.code_files = QListWidget()
        self.code_files.setMaximumWidth(120)
        self.code_files.currentRowChanged.connect(self.select_code_file)
        row.addWidget(self.code_files, 1)
        self.code_editor = QPlainTextEdit()
        self.code_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if hasattr(QPlainTextEdit, "LineWrapMode") else QPlainTextEdit.NoWrap)
        code_font = QFont("Consolas", 10)
        self.code_editor.setFont(code_font)
        self.code_editor.setTabStopDistance(QFontMetrics(code_font).horizontalAdvance("  "))
        self.code_editor.setStyleSheet("background: #0b1020; color: #dce7ff; border: 1px solid #242936; border-radius: 12px; padding: 10px;")
        self.code_editor.textChanged.connect(self.on_code_editor_text_changed)
        row.addWidget(self.code_editor, 3)
        layout.addLayout(row)
        controls = QHBoxLayout()
        add_btn = QPushButton("新建文件")
        add_btn.clicked.connect(self.add_code_file)
        apply_btn = QPushButton("保存代码")
        apply_btn.clicked.connect(self.apply_code_file)
        delete_btn = QPushButton("删除文件")
        delete_btn.clicked.connect(self.delete_code_file)
        format_btn = QPushButton("简单格式化")
        format_btn.clicked.connect(self.format_code_file)
        external_btn = QPushButton("打开导出目录")
        external_btn.clicked.connect(self.open_generated_output_dir)
        stub_btn = QPushButton("一键生成缺失回调")
        stub_btn.clicked.connect(self.generate_missing_callbacks)
        cond_btn = QPushButton("一键创建条件函数")
        cond_btn.clicked.connect(self.generate_condition_callbacks)
        controls.addWidget(add_btn)
        controls.addWidget(apply_btn)
        controls.addWidget(delete_btn)
        controls.addWidget(format_btn)
        controls.addWidget(external_btn)
        controls.addWidget(stub_btn)
        controls.addWidget(cond_btn)
        layout.addLayout(controls)
        layout.addWidget(QLabel("回调补齐清单（来自 codegen 契约）："))
        self.callback_gap_output = QPlainTextEdit()
        self.callback_gap_output.setReadOnly(True)
        layout.addWidget(self.callback_gap_output)
        layout.addWidget(QLabel("Custom code is saved in graph.custom_files and emitted beside generated application files."))
        return widget

    def _build_json_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.graph_json_editor = QPlainTextEdit()
        apply_btn = QPushButton("Apply Full Graph JSON")
        apply_btn.clicked.connect(self.apply_full_json)
        layout.addWidget(self.graph_json_editor)
        layout.addWidget(apply_btn)
        return widget
