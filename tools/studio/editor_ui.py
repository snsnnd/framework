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
        QCheckBox, QComboBox, QFormLayout, QGraphicsScene, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
        QPlainTextEdit, QPushButton, QSplitter, QTabBar, QTabWidget,
        QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QKeySequence
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QFormLayout, QGraphicsScene, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
        QPlainTextEdit, QPushButton, QShortcut, QSplitter, QTabBar,
        QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QWidget = QTabWidget = QTableWidget = object
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
            toolbar.addAction("快捷键", self.show_shortcuts)

        root_splitter = QSplitter()
        self.setCentralWidget(root_splitter)

        left = QWidget()
        left.setObjectName("NavRail")
        left.setMinimumWidth(180)
        left.setMaximumWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        title = QLabel("EFW")
        title.setStyleSheet("font-size: 18pt; font-weight: 700; color: #ffffff;")
        left_layout.addWidget(title)
        left_layout.addWidget(QLabel("Project Builder"))
        self.workflow_list = QListWidget()
        workflow_steps = [
            ("项目总览", "dashboard"),
            ("模块装配", "assembly"),
            ("资源规划", "resources"),
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
        shortcuts_btn = QPushButton("⚙ 快捷键设定")
        shortcuts_btn.clicked.connect(self.open_shortcuts_editor)
        left_layout.addWidget(shortcuts_btn)
        root_splitter.addWidget(left)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setMinimumWidth(360)
        self.workspace_tabs.addTab(self._build_dashboard_tab(), "项目总览")
        self.workspace_tabs.addTab(self._build_assembly_tab(), "模块装配")

        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        self.page_tabs = QTabBar()
        self.page_tabs.setExpanding(False)
        self.page_tabs.setTabsClosable(True)
        self.page_tabs.currentChanged.connect(self.switch_page_tab)
        self.page_tabs.tabCloseRequested.connect(self.close_page_tab)
        canvas_layout.addWidget(self.page_tabs)
        page_controls = QHBoxLayout()
        page_controls.addWidget(QLabel("关系视图：用页面标签进入模块/状态机/Topic；连线从输出端口拖到输入端口。"))
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
        self.module_scope_label = QLabel("当前视图：根项目")
        canvas_layout.addWidget(self.module_scope_label)
        self.scene = QGraphicsScene()
        self.view = BlueprintView(self.scene, self)
        canvas_layout.addWidget(self.view)
        self.workspace_tabs.addTab(canvas, "关系视图")
        self.workspace_tabs.addTab(self._build_release_tab(), "生成发布")
        root_splitter.addWidget(self.workspace_tabs)

        inspector = QWidget()
        inspector.setMinimumWidth(260)
        inspector.setMaximumWidth(720)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        inspector_title = QLabel("Inspector")
        inspector_title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #ffffff;")
        inspector_layout.addWidget(inspector_title)
        self.inspector_nav = QListWidget()
        inspector_layout.addWidget(self.inspector_nav)
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self._build_structure_tab(), "项目结构")
        self.right_tabs.addTab(self._build_properties_tab(), "属性表单")
        self.right_tabs.addTab(self._build_code_tab(), "代码")
        self.right_tabs.addTab(self._build_validation_tab(), "实时校验")
        self.right_tabs.addTab(self._build_mapping_tab(), "生成映射")
        self.right_tabs.addTab(self._build_file_tree_tab(), "文件树预览")
        self.right_tabs.addTab(self._build_schedule_tab(), "任务调度")
        self.right_tabs.addTab(self._build_pin_planner_tab(), "Board Profile / Pin Planner")
        self.right_tabs.addTab(self._build_json_tab(), "Graph JSON")
        for index in range(self.right_tabs.count()):
            item = QListWidgetItem(self.right_tabs.tabText(index), self.inspector_nav)
            item.setData(role, index)
        self.inspector_nav.currentRowChanged.connect(self.switch_inspector_panel)
        self.inspector_nav.setCurrentRow(0)
        self.right_tabs.tabBar().hide()
        inspector_layout.addWidget(self.right_tabs, 1)
        root_splitter.addWidget(inspector)
        root_splitter.setChildrenCollapsible(True)
        root_splitter.setSizes([210, 620, 320])

    def switch_inspector_panel(self, row: int) -> None:
        if hasattr(self, "right_tabs") and 0 <= row < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(row)

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
        open_code_btn.clicked.connect(lambda: self.set_right_tab("代码"))
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
        self.structure_output = QPlainTextEdit()
        self.structure_output.setReadOnly(True)
        layout.addWidget(self.structure_output)
        return widget

    def _build_file_tree_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.file_tree_output = QPlainTextEdit()
        self.file_tree_output.setReadOnly(True)
        layout.addWidget(self.file_tree_output)
        return widget

    def _build_schedule_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
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
Delete / Backspace 删除当前卡片
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
        stub_btn = QPushButton("一键生成缺失回调")
        stub_btn.clicked.connect(self.generate_missing_callbacks)
        cond_btn = QPushButton("一键创建条件函数")
        cond_btn.clicked.connect(self.generate_condition_callbacks)
        controls.addWidget(add_btn)
        controls.addWidget(apply_btn)
        controls.addWidget(delete_btn)
        controls.addWidget(format_btn)
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
