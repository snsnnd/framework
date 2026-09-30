#!/usr/bin/env python3
"""UI construction mixin for the EFW visual editor.

Extracted from editor.py: all _build_* methods that construct the
workspace tabs, inspector panels, and navigation layout.
"""

from __future__ import annotations

from typing import Any

import importlib.util

from studio.qt_compat import (
    QT_LIB,
    Qt,
    QBrush, QColor, QFont, QFontMetrics, QKeySequence, QShortcut,
    QCheckBox, QComboBox, QDockWidget, QFormLayout, QGraphicsScene,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QMainWindow, QPlainTextEdit, QPushButton,
    QSplitter, QStackedWidget, QTabBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QToolBar, QVBoxLayout, QWidget, QToolBox,
)

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
        
        # Search box
        self.palette_search = QLineEdit()
        self.palette_search.setPlaceholderText("搜索模板… (双击插入)")
        self.palette_search.textChanged.connect(self.filter_palette)
        left_layout.addWidget(self.palette_search)
        
        # Template palette
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
                item = QListWidgetItem(f"  {display_label(node_type)}", self.palette)
                item.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, node_type)
                item.setData(Qt.ItemDataRole.UserRole + 1 if hasattr(Qt, "ItemDataRole") else Qt.UserRole + 1, category)
                theme = node_theme(template_type)
                item.setBackground(QBrush(QColor(theme["bg"])))
                item.setForeground(QBrush(QColor("#f4fbff")))
        left_layout.addWidget(self.palette)
        
        # Quick action buttons (compact)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加")
        add_btn.setToolTip("添加选中模板到画布 (Ctrl+M)")
        add_btn.clicked.connect(self.add_selected_card)
        btn_row.addWidget(add_btn)
        
        backdrop_btn = QPushButton("□ 分组")
        backdrop_btn.setToolTip("创建分组区域 (Ctrl+Shift+B)")
        backdrop_btn.clicked.connect(self.create_backdrop_from_selection)
        btn_row.addWidget(backdrop_btn)
        
        flip_btn = QPushButton("↔ 翻转")
        flip_btn.setToolTip("翻转选中卡片接口 (F)")
        flip_btn.clicked.connect(self.flip_selected_node_ports)
        btn_row.addWidget(flip_btn)
        left_layout.addLayout(btn_row)
        # Hint: double-click canvas or press Tab to quick-add node

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
        self.scene.selectionChanged.connect(self.handle_scene_selection_changed)
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
        self.bottom_tabs.addTab(self._build_debug_tab(), "运行分析")
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

    def rebuild_inspector_nav(self, hidden_tabs: set[str] | None = None) -> None:
        if not hasattr(self, "inspector_nav") or not hasattr(self, "right_tabs"):
            return
        if hidden_tabs is None:
            hidden_tabs = set()
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        current_index = self.right_tabs.currentIndex() if hasattr(self.right_tabs, "currentIndex") else 0
        self.inspector_nav.blockSignals(True)
        self.inspector_nav.clear()
        current_row = 0
        row = 0
        for index in range(self.right_tabs.count()):
            title = self.right_tabs.tabText(index)
            # Skip advanced tabs if not enabled
            if not self._advanced_inspector_enabled and title in self._advanced_tab_titles:
                continue
            # Skip hidden tabs based on node type
            if title in hidden_tabs:
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
        # Dashboard
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
        # Assembly
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
        # Release - use QTextEdit for HTML support
        self.release_output = QTextEdit()
        self.release_output.setReadOnly(True)
        self.release_output.setStyleSheet("QTextEdit { background-color: #0B101A; border: 1px solid #242D40; border-radius: 4px; padding: 8px; }")
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
        title_row = QHBoxLayout()
        self.selected_label = QLabel("未选择卡片")
        title_row.addWidget(self.selected_label, 1)
        self.dev_mode_btn = QPushButton("{ }")
        self.dev_mode_btn.setCheckable(True)
        self.dev_mode_btn.clicked.connect(self.toggle_property_dev_mode)
        title_row.addWidget(self.dev_mode_btn)
        layout.addLayout(title_row)

        self.property_stack = QStackedWidget()
        form_page = QWidget()
        form_layout = QVBoxLayout(form_page)
        form_layout.setContentsMargins(0, 0, 0, 0)
        self.property_sections = QToolBox()
        self.property_tables_by_section = {}
        section_defs = [
            ("basic", "基础信息", True),
            ("parameters", "参数", True),
        ]
        for key, title, _expanded in section_defs:
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(4, 4, 4, 4)
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(["属性", "值", "说明"])
            table.setMinimumHeight(120)
            section_layout.addWidget(table)
            self.property_tables_by_section[key] = table
            self.property_sections.addItem(section, title)
        self.property_sections.setCurrentIndex(0)
        form_layout.addWidget(self.property_sections)
        apply_form_btn = QPushButton("应用表单")
        apply_form_btn.clicked.connect(self.apply_property_form)
        form_layout.addWidget(apply_form_btn)
        self.property_stack.addWidget(form_page)

        json_page = QWidget()
        json_layout = QVBoxLayout(json_page)
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.addWidget(QLabel("JSON 编辑"))
        self.node_json_editor = QPlainTextEdit()
        self.node_json_editor.setMaximumHeight(220)
        json_layout.addWidget(self.node_json_editor)
        apply_btn = QPushButton("应用 JSON")
        apply_btn.clicked.connect(self.apply_node_json)
        json_layout.addWidget(apply_btn)
        self.property_stack.addWidget(json_page)

        layout.addWidget(self.property_stack)
        # Callback preview
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
        delete_btn = QPushButton("删除卡片")
        delete_btn.clicked.connect(self.delete_selected_node)
        layout.addWidget(delete_btn)
        return widget

    def toggle_property_dev_mode(self) -> None:
        if not hasattr(self, "property_stack"):
            return
        self.property_stack.setCurrentIndex(1 if self.dev_mode_btn.isChecked() else 0)

    def _build_pin_planner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Board profile selection with auto-apply
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Board Profile:"))
        self.board_profile_edit = QComboBox()
        self.board_profile_edit.addItems(list(BOARD_PROFILES))
        self.board_profile_edit.currentTextChanged.connect(self._on_board_profile_changed)
        profile_row.addWidget(self.board_profile_edit)
        layout.addLayout(profile_row)
        
        # Resource summary
        self.resource_summary = QLabel()
        self.resource_summary.setWordWrap(True)
        self.resource_summary.setStyleSheet("background: #1a2332; border: 1px solid #2a3848; border-radius: 6px; padding: 8px; color: #b8c3d8;")
        layout.addWidget(self.resource_summary)
        
        # Pin tables by category
        self.pin_tabs = QTabWidget()
        self.pin_tabs.setTabPosition(QTabWidget.TabPosition.North if hasattr(QTabWidget, "TabPosition") else QTabWidget.North)
        
        # GPIO tab
        self.gpio_table = QTableWidget(0, 5)
        self.gpio_table.setHorizontalHeaderLabels(["节点", "引脚", "端口", "引脚号", "功能/备注"])
        self.gpio_table.horizontalHeader().setStretchLastSection(True)
        self.pin_tabs.addTab(self.gpio_table, "GPIO")
        
        # PWM tab
        self.pwm_table = QTableWidget(0, 5)
        self.pwm_table.setHorizontalHeaderLabels(["节点", "定时器", "通道", "频率", "功能/备注"])
        self.pwm_table.horizontalHeader().setStretchLastSection(True)
        self.pin_tabs.addTab(self.pwm_table, "PWM")
        
        # Communication tab
        self.comm_table = QTableWidget(0, 5)
        self.comm_table.setHorizontalHeaderLabels(["节点", "类型", "总线ID", "引脚", "功能/备注"])
        self.comm_table.horizontalHeader().setStretchLastSection(True)
        self.pin_tabs.addTab(self.comm_table, "通信")
        
        # ADC tab
        self.adc_table = QTableWidget(0, 5)
        self.adc_table.setHorizontalHeaderLabels(["节点", "ADC", "通道", "分辨率", "功能/备注"])
        self.adc_table.horizontalHeader().setStretchLastSection(True)
        self.pin_tabs.addTab(self.adc_table, "ADC")
        
        layout.addWidget(self.pin_tabs)
        
        # Apply button
        apply_btn = QPushButton("应用 Pin Planner")
        apply_btn.clicked.connect(self.apply_pin_planner)
        apply_btn.setStyleSheet("QPushButton { background-color: #1a6b3c; } QPushButton:hover { background-color: #1f7d45; }")
        layout.addWidget(apply_btn)
        
        return widget

    def _on_board_profile_changed(self, profile_name: str) -> None:
        """Auto-apply board profile when changed."""
        if profile_name and hasattr(self, 'graph'):
            self.apply_board_profile_defaults()

    def _build_validation_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # Validation
        self.validation_list = QListWidget()
        self.validation_list.itemClicked.connect(self.open_validation_item)
        layout.addWidget(self.validation_list)
        self.validation_output = QTextEdit()
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
        # Structure
        self.structure_output = QPlainTextEdit()
        self.structure_output.setReadOnly(True)
        layout.addWidget(self.structure_output)
        return widget

    def _build_file_tree_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # File tree
        self.file_tree_output = QPlainTextEdit()
        self.file_tree_output.setReadOnly(True)
        layout.addWidget(self.file_tree_output)
        return widget

    def _build_schedule_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # Schedule - use QTextEdit for HTML support
        self.schedule_output = QTextEdit()
        self.schedule_output.setReadOnly(True)
        layout.addWidget(self.schedule_output)
        return widget

    def _build_debug_tab(self) -> QWidget:
        """Build the debug/visualization tab."""
        # Use DebugMixin's _build_debug_panel if available
        if hasattr(self, '_build_debug_panel'):
            return self._build_debug_panel()
        
        # Fallback: simple placeholder
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("运行分析面板 - 请刷新查看可视化")
        label.setStyleSheet("color: #8F9DB2; padding: 20px;")
        layout.addWidget(label)
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

画布操作
鼠标左键拖空白处  平移画布
Ctrl + 鼠标左键   框选多个节点
Ctrl + 滚轮       缩放关系视图
双击空白处        打开快速插入
拖动已选中节点    移动该节点；如果已经多选，则一起移动

线条说明
实线 data_flow            运行时数据流。常见于 Sensor -> Process、Process -> Algorithm / Actuator；为了便于区分，它会有较明显的流动效果。
点线 hardware_dependency  硬件依赖。常见于 HAL -> Sensor / Actuator；这类边表示接线或底层依赖，不强调运行方向，所以不做流动动画。
虚线 schedule            调度或周期关系。常见于 task / flow 对运行单元的驱动。
虚线 event               事件或主题发布订阅关系。
虚线 contains            容器或归属关系，例如根项目里的模块组织关系。
点线 code                自定义代码文件与运行节点的关联。
青绿色状态线            状态机迁移相关关系。

说明
HAL 和 Sensor 的线现在通常不会流动，是因为它们多数会被识别成 hardware_dependency，表示“依赖哪路硬件”而不是“数据正在沿这条边流动”。
Sensor 和 Process 的线与其他线差异更大是刻意保留的视觉区分：这类边最接近主数据通路，做得更明显更容易一眼看出系统的数据入口和处理链。

通信与状态机
event.publisher 现在会生成可调用的发布包装函数：`app_publish_xxx(data, size)`；如果 payload 类型可推断，还会生成 `app_publish_xxx_typed(...)` 和标量版 `app_publish_xxx_value(...)`。
如果填写 `interval_ms`，自动发布会按该最小间隔节流；如果 payload 与上次完全相同，也会自动跳过重复发布。
event.subscriber 仍会生成 `efw_topic_subscribe(...)` 绑定和回调声明。
状态机现在会生成 `app_sm_xxx_tick()`、`app_sm_xxx_dispatch_event()`、`app_sm_xxx_transition_to()`、`app_sm_xxx_current_state()`，并提供系统级 `app_dispatch_event(...)` 入口。
`event_trigger` 现在必须写成明确格式：`topic:<event.topic节点id>` 或 `event:<事件名>`。例如：`topic:root__topic__start_evt`、`event:start`。

当前阶段先固定快捷键，避免设置项和项目文件格式过早复杂化；如果后续用户频繁冲突，再加入可配置快捷键。"""

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "快捷键", self.shortcuts_text())

    def show_welcome_guide(self) -> None:
        """Show welcome guide for first-time users."""
        guide_text = """<h2>欢迎使用 EFW Studio</h2>

<p><b>快速开始：</b></p>
<ol>
<li><b>左侧模板库</b> - 双击卡片插入到画布</li>
<li><b>拖拽连接</b> - 从端口圆点拖线到另一个端口</li>
<li><b>F 键</b> - 翻转选中卡片的接口方向</li>
<li><b>Tab 键</b> - 快速搜索插入卡片</li>
<li><b>Ctrl+Shift+G</b> - 一键生成代码</li>
</ol>

<p><b>常用操作：</b></p>
<ul>
<li>Ctrl+S 保存 | Ctrl+Z 撤销 | Ctrl+Y 重做</li>
<li>Delete 删除选中 | Ctrl+M 添加卡片</li>
<li>鼠标滚轮缩放画布</li>
</ul>

<p><b>提示：</b>按 <code>F1</code> 随时查看快捷键</p>"""
        
        msg = QMessageBox(self)
        msg.setWindowTitle("EFW Studio 使用指南")
        msg.setTextFormat(Qt.TextFormat.RichText if hasattr(Qt, "TextFormat") else Qt.RichText)
        msg.setText(guide_text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok if hasattr(QMessageBox, "StandardButton") else QMessageBox.Ok)
        msg.exec()

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
        
        # Add syntax highlighter
        from studio.c_highlighter import CHighlighter
        self.code_highlighter = CHighlighter(self.code_editor.document())
        
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
        # Callback list - use QTextEdit for HTML support
        self.callback_gap_output = QTextEdit()
        self.callback_gap_output.setReadOnly(True)
        layout.addWidget(self.callback_gap_output)

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
