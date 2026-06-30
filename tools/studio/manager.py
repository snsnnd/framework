#!/usr/bin/env python3
"""PyQt project manager for EFW visual-codegen projects.

The visual editor edits one graph at a time. This project manager adds a thin
workspace layer around that graph: it remembers the graph file, output
application directory, target board profile, and notes so users can manage a
small embedded project without repeatedly typing paths.
"""

from __future__ import annotations

import json
import copy
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from studio.qt_compat import (
    QT_LIB, is_qt_available,
    QApplication, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QPlainTextEdit, QShortcut,
    QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget,
    QFont, QKeySequence,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { background: #0f1117; color: #e6e9ef; font-family: "Noto Sans CJK SC", "Microsoft YaHei", "SF Pro Display", "Segoe UI", "DejaVu Sans"; font-size: 10pt; }
QToolBar { background: #0f1117; border-bottom: 1px solid #242936; spacing: 8px; padding: 6px; }
QToolButton, QPushButton {
    background: #1c2333;
    color: #f4f7fb;
    border: 1px solid #2f3a52;
    border-radius: 10px;
    padding: 7px 12px;
}
QToolButton:hover, QPushButton:hover { background: #26324a; border-color: #5f8cff; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #151a24; color: #9ba7bd; padding: 8px 14px; border: 0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #6ea8fe; background: #111722; }
QListWidget, QPlainTextEdit, QLineEdit, QComboBox {
    background: #151a24;
    color: #e6e9ef;
    border: 1px solid #242936;
    border-radius: 12px;
    selection-background-color: #355c9a;
    padding: 4px;
}
QLabel { color: #dce3f0; }

/* Scrollbar Styles */
QScrollBar:vertical {
    background-color: #111722;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #2a3548;
    min-height: 30px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background-color: #3a4a60;
}
QScrollBar::handle:vertical:pressed {
    background-color: #4a5a70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    background: none;
}

QScrollBar:horizontal {
    background-color: #111722;
    height: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background-color: #2a3548;
    min-width: 30px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #3a4a60;
}
QScrollBar::handle:horizontal:pressed {
    background-color: #4a5a70;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
    background: none;
}
"""

PROJECT_SCHEMA_VERSION = 1
PROJECT_SUFFIX = ".efw_project.json"
RECENT_FILE = REPO_ROOT / ".efw_projects" / "recent.json"


def default_project() -> dict[str, Any]:
    return {
        "kind": "efw.project",
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": "generic_embedded_app",
        "description": "EFW Studio 项目文件。它保存项目说明、Graph 路径、输出目录和目标板卡配置。",
        "graph_path": "examples/graphs/generic_embedded_app.json",
        "output_dir": "application/generated_generic_embedded_app",
        "board_profile": "generic-mock",
        "notes": "Use the graph editor to edit cards/code, then generate application/. Put board-specific glue in graph.board_adapters.",
        "workflow": [
            "双击最近项目或打开 .efw_project.json 后，先检查项目名、Graph JSON、输出目录和 Board Profile。",
            "点击“打开当前项目”进入项目装配，编辑卡片、关系和 custom_files。",
            "回到项目页执行实时校验，通过后生成 application。",
        ],
    }


def project_slug(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", name.strip()).strip("_")
    return slug or "new_efw_project"


def blank_graph(name: str, board_profile: str) -> dict[str, Any]:
    return {
        "project": {"name": name, "tick_ms": 1},
        "board": {"profile": board_profile, "pin_plan": []},
        "nodes": [
            {
                "id": "app_module",
                "type": "project.module",
                "display_name": "应用模块",
                "description": "项目的第一个模块。",
            }
        ],
        "edges": [],
        "flows": [],
        "tasks": [],
        "custom_files": [{"path": "app_custom.c", "content": "#include \"efw/efw.h\"\n"}],
        "ui": {"positions": {"app_module": [40, 40]}},
    }


def rel_or_abs(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_recent_projects() -> list[str]:
    if not RECENT_FILE.exists():
        return []
    data = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and str(item).endswith(PROJECT_SUFFIX)]


def save_recent_projects(paths: list[str]) -> None:
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    unique: list[str] = []
    for item in paths:
        if item not in unique:
            unique.append(item)
    RECENT_FILE.write_text(json.dumps(unique[:20], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_recent_project(path_text: str) -> None:
    save_recent_projects([item for item in load_recent_projects() if item != path_text])


def normalize_project_descriptor(project: dict[str, Any], project_path: Path) -> dict[str, Any]:
    normalized = dict(project)
    sibling_graph = project_path.parent / "graph.json"
    graph_path_text = str(normalized.get("graph_path", ""))
    if sibling_graph.exists() and graph_path_text in {"", "examples/graphs/generic_embedded_app.json"}:
        normalized["graph_path"] = display_path(sibling_graph)
        if not normalized.get("name") or normalized.get("name") == "generic_embedded_app":
            try:
                graph = json.loads(sibling_graph.read_text(encoding="utf-8"))
                graph_name = graph.get("project", {}).get("name") if isinstance(graph, dict) else None
                normalized["name"] = str(graph_name or project_path.stem.replace(PROJECT_SUFFIX, ""))
            except Exception:  # noqa: BLE001 - best effort descriptor migration.
                normalized["name"] = project_path.stem.replace(PROJECT_SUFFIX, "")
        if not normalized.get("output_dir") or normalized.get("output_dir") == "application/generated_generic_embedded_app":
            normalized["output_dir"] = f"application/generated_{project_slug(str(normalized.get('name', 'efw_project')))}"
    return normalized


class ProjectManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"EFW 可视化项目工作台 ({QT_LIB})")
        self.resize(1060, 660)
        self.setMinimumSize(860, 520)
        self.project_path: Path | None = None
        self.project = default_project()
        self.loading_recent_path: Path | None = None
        self.graph_editor_windows: list[VisualEditorWindow] = []
        self.embedded_editor: VisualEditorWindow | None = None
        self._project_dirty = False
        self._form_sync_in_progress = False
        self.setStyleSheet(WORKBENCH_STYLESHEET)
        self._build_ui()
        self._state_label = QLabel("已保存")
        self.statusBar().addPermanentWidget(self._state_label)
        self.refresh_recent_list()
        self.load_project_to_form()
        self.update_workspace_state()

    def _build_ui(self) -> None:
        toolbar = QToolBar("项目工具栏")
        self.addToolBar(toolbar)
        toolbar.addAction("新建", self.new_project)
        toolbar.addAction("项目创建向导", self.project_wizard)
        toolbar.addAction("打开", self.open_project)
        toolbar.addAction("打开上次项目", self.open_last_project)
        toolbar.addAction("保存全部", self.save_project)
        toolbar.addAction("项目另存为", self.save_project_as)
        
        # Add separator before generation actions
        toolbar.addSeparator()
        toolbar.addAction("一键生成", self.quick_generate).setToolTip("校验并生成 Application（Ctrl+Shift+G）")
        toolbar.addAction("运行分析", self.show_debug_analysis)
        
        # Add shortcut for quick generate
        self.quick_generate_shortcut = QShortcut(QKeySequence("Ctrl+Shift+G"), self)
        self.quick_generate_shortcut.activated.connect(self.quick_generate)
        
        # Menu bar
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("新建项目", self.new_project)
        file_menu.addAction("项目创建向导", self.project_wizard)
        file_menu.addSeparator()
        file_menu.addAction("打开项目", self.open_project)
        file_menu.addAction("打开上次项目", self.open_last_project)
        file_menu.addSeparator()
        file_menu.addAction("保存全部", self.save_project)
        file_menu.addAction("项目另存为", self.save_project_as)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        
        # Import menu
        import_menu = menubar.addMenu("导入")
        import_menu.addAction("芯片选择向导...", self.open_chip_wizard)
        import_menu.addAction("导入芯片配置文件...", self.import_board_profile)
        import_menu.addAction("导入硬件配置文件...", self.import_hardware_config)
        import_menu.addSeparator()
        import_menu.addAction("导出当前 Board Profile", self.export_board_profile)
        
        # View menu
        self.view_menu = menubar.addMenu("视图")
        self.view_menu.addAction("资源", self.toggle_resource_dock)
        self.view_menu.addAction("属性", self.toggle_inspector_dock)
        self.view_menu.addAction("输出", self.toggle_output_dock)
        self.view_menu.addSeparator()
        self.view_menu.addAction("重置布局", self.reset_editor_layout)
        
        # Help menu
        help_menu = menubar.addMenu("帮助")
        help_menu.addAction("快捷键", self.show_shortcuts_dialog)
        help_menu.addSeparator()
        help_menu.addAction("关于", self.show_about_dialog)
        
        self.toggle_output_shortcut = QShortcut(QKeySequence("Ctrl+`"), self)
        self.toggle_output_shortcut.activated.connect(self.toggle_output_dock)

        self.workspace_tabs = QTabWidget()
        self.setCentralWidget(self.workspace_tabs)

        project_page = QWidget()
        project_layout = QVBoxLayout(project_page)
        splitter = QSplitter()
        project_layout.addWidget(splitter)
        self.workspace_tabs.addTab(project_page, "项目")

        left = QWidget()
        left.setMinimumWidth(180)
        left.setMaximumWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("最近项目"))
        self.recent_list = QListWidget()
        self.recent_list.currentItemChanged.connect(lambda current, _previous: self.open_recent_project(current) if current else None)
        self.recent_list.itemClicked.connect(self.open_recent_project)
        self.recent_list.itemDoubleClicked.connect(self.open_recent_project)
        left_layout.addWidget(self.recent_list)
        splitter.addWidget(left)

        editor = QWidget()
        editor.setMinimumWidth(360)
        root = QVBoxLayout(editor)
        form = QFormLayout()
        self.project_file_label = QLabel("未保存")
        self.output_edit = QLineEdit()
        self.board_edit = QComboBox()
        self.board_edit.addItems(list(BOARD_PROFILES))
        form.addRow("项目文件", self.project_file_label)
        form.addRow("输出 application", self._path_row(self.output_edit, self.choose_output_dir))
        form.addRow("Board Profile", self.board_edit)
        root.addLayout(form)
        self.project_summary = QLabel("项目摘要：未加载项目")
        self.project_summary.setWordWrap(True)
        self.project_summary.setStyleSheet("background: #151a24; border: 1px solid #242936; border-radius: 12px; padding: 8px; color: #b8c3d8;")
        root.addWidget(self.project_summary)
        root.addWidget(QLabel("说明 / 交接清单"))
        self.notes_edit = QPlainTextEdit()
        root.addWidget(self.notes_edit)
        self.save_state_label = QLabel("保存状态：已保存")
        self.save_state_label.setWordWrap(True)
        self.save_state_label.setStyleSheet("background: #151a24; border: 1px solid #242936; border-radius: 12px; padding: 8px; color: #b8c3d8;")
        root.addWidget(self.save_state_label)

        buttons = QHBoxLayout()
        for text, callback in [
            ("一键生成", self.quick_generate),
            ("打开装配", self.open_graph_editor),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        
        # Style the quick generate button
        buttons.itemAt(0).widget().setStyleSheet("QPushButton { background-color: #1a6b3c; } QPushButton:hover { background-color: #1f7d45; }")
        
        root.addLayout(buttons)
        splitter.addWidget(editor)
        splitter.setChildrenCollapsible(True)
        splitter.setSizes([220, 680])
        self.output_edit.textChanged.connect(self._on_project_form_changed)
        self.board_edit.currentTextChanged.connect(self._on_project_form_changed)
        self.notes_edit.textChanged.connect(self._on_project_form_changed)

    def _path_row(self, edit: QLineEdit, callback) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        button = QPushButton("浏览")
        button.clicked.connect(callback)
        layout.addWidget(button)
        return widget

    def load_project_to_form(self) -> None:
        self._form_sync_in_progress = True
        self.project_file_label.setText(display_path(self.project_path) if self.project_path else "未保存")
        self.project_summary.setText(
            f"项目：{self.project.get('name', '')}\n"
            f"Graph：{self.project.get('graph_path', '')}\n"
            f"说明：{self.project.get('description', '')}"
        )
        self.output_edit.setText(str(self.project.get("output_dir", "")))
        profile = str(self.project.get("board_profile", "generic-mock"))
        if self.board_edit.findText(profile) < 0:
            self.board_edit.addItem(profile)
        self.board_edit.setCurrentText(profile)
        self.notes_edit.setPlainText(str(self.project.get("notes", "")))
        self._form_sync_in_progress = False
        self._project_dirty = False
        self.update_workspace_state()

    def apply_form_to_project(self) -> None:
        updated = dict(default_project())
        updated.update(self.project)
        updated.update({
            "kind": "efw.project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "output_dir": self.output_edit.text().strip(),
            "board_profile": self.board_edit.currentText().strip() or "generic-mock",
            "notes": self.notes_edit.toPlainText(),
        })
        self.project = updated
        self.update_workspace_state()

    def _on_project_form_changed(self, *_args) -> None:
        if self._form_sync_in_progress:
            return
        self._project_dirty = True
        self.update_workspace_state()

    def current_dirty_kinds(self) -> list[str]:
        kinds: list[str] = []
        if self._project_dirty:
            kinds.append("项目")
        if self.embedded_editor is not None:
            if self.embedded_editor._is_dirty:
                kinds.append("Graph")
            if self.embedded_editor.code_buffer_is_dirty():
                kinds.append("Code")
        return kinds

    def update_workspace_state(self) -> None:
        kinds = self.current_dirty_kinds()
        state_text = "已保存" if not kinds else "未保存：" + " / ".join(kinds)
        self._state_label.setText(state_text)
        self.save_state_label.setText(f"保存状态：{state_text}\n提示：在工作台里点击“保存全部”会同时保存项目描述、当前 Graph 和已应用到 Graph 的代码文件。")
        suffix = " *" if kinds else ""
        self.setWindowTitle(f"EFW 可视化项目工作台 ({QT_LIB}){suffix}")

    def refresh_recent_list(self) -> None:
        self.recent_list.blockSignals(True)
        self.recent_list.clear()
        valid_paths: list[str] = []
        for path in load_recent_projects():
            if rel_or_abs(path).exists():
                valid_paths.append(path)
                QListWidgetItem(path, self.recent_list)
        if valid_paths != load_recent_projects():
            save_recent_projects(valid_paths)
        self.recent_list.blockSignals(False)

    def add_recent_project(self, path: Path) -> None:
        current = load_recent_projects()
        text = display_path(path)
        save_recent_projects([text] + [item for item in current if item != text])
        self.refresh_recent_list()

    def _confirm_workspace_discard_changes(self) -> bool:
        if self._project_dirty:
            answer = QMessageBox.question(
                self,
                "未保存的项目配置",
                "当前项目页有未保存更改，是否先保存后再继续？",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save:
                self.save_project()
                return not self._project_dirty
        if self.embedded_editor is not None and not self.embedded_editor._confirm_discard_changes():
            return False
        return True

    def new_project(self) -> None:
        if not self._confirm_workspace_discard_changes():
            return
        name, ok = QInputDialog.getText(self, "新建 EFW 项目", "项目名", text="new_efw_project")
        if not ok or not name.strip():
            return
        board = self.board_edit.currentText().strip() or "generic-mock"
        output_dir = f"application/generated_{project_slug(name)}"
        self.create_project_files(name.strip(), blank_graph(name.strip(), board), output_dir, board)

    def project_wizard(self) -> None:
        if not self._confirm_workspace_discard_changes():
            return
        templates = {
            "空白项目": ("new_efw_project", None, "application/generated_new_efw_project", "generic-mock"),
            "通用嵌入式应用": ("generic_embedded_app", "examples/graphs/generic_embedded_app.json", "application/generated_generic_embedded_app", "generic-mock"),
            "循迹小车": ("line_tracking_car", "examples/graphs/line_tracking_car.json", "application/generated_line_tracking_car", "robot-line-tracking"),
            "循迹 + 自定义代码": ("line_tracking_car_custom", "examples/graphs/line_tracking_car_with_custom_code.json", "application/generated_line_tracking_car_custom", "robot-line-tracking"),
        }
        choice, ok = QInputDialog.getItem(self, "项目创建向导", "选择项目模板", list(templates), 0, False)
        if not ok or not choice:
            return
        name, graph_path, output_dir, board = templates[choice]
        custom_name, ok = QInputDialog.getText(self, "项目创建向导", "项目名", text=name)
        if ok and custom_name:
            name = custom_name
            output_dir = f"application/generated_{project_slug(custom_name)}"
        graph = blank_graph(name, board) if graph_path is None else json.loads(rel_or_abs(graph_path).read_text(encoding="utf-8"))
        self.create_project_files(name, graph, output_dir, board)

    def create_project_files(self, name: str, graph: dict[str, Any], output_dir: str, board: str) -> None:
        slug = project_slug(name)
        default_dir = REPO_ROOT / ".efw_projects" / slug
        
        # Ask for project directory
        project_dir_str = QFileDialog.getExistingDirectory(
            self,
            "选择项目目录",
            str(default_dir),
            QFileDialog.Option.ShowDirsOnly if hasattr(QFileDialog, "Option") else QFileDialog.ShowDirsOnly
        )
        
        if not project_dir_str:
            # If user cancels, use default directory
            project_dir = default_dir
        else:
            project_dir = Path(project_dir_str) / slug
        
        # Create project directory
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Project file paths
        project_path = project_dir / f"{slug}{PROJECT_SUFFIX}"
        graph_path = project_dir / "graph.json"
        
        # Check if files exist
        if graph_path.exists() or project_path.exists():
            answer = QMessageBox.question(
                self,
                "覆盖确认",
                f"项目目录已存在文件：\n{display_path(project_dir)}\n\n是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes | QMessageBox.No
            )
            yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
            if answer != yes:
                return
        
        # Write graph file
        graph.setdefault("project", {})["name"] = name
        graph.setdefault("board", {})["profile"] = board
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        
        # Set project data
        self.project_path = project_path
        self.project = {
            "kind": "efw.project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": name,
            "description": f"{name} 的 EFW Studio 项目描述文件。",
            "graph_path": "graph.json",
            "output_dir": output_dir,
            "board_profile": board,
            "notes": "由项目创建向导生成。建议先打开项目装配检查卡片、Board Profile 和 Pin Planner，再生成 application/。",
            "workflow": default_project()["workflow"],
        }
        
        # Save project file
        self.save_project()
        self.load_project_to_form()
        
        # Auto-open graph editor after project creation
        self.open_graph_editor()
        
        self.statusBar().showMessage(f"项目已创建并打开：{display_path(project_dir)}", 7000)

    def open_project(self) -> None:
        if not self._confirm_workspace_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开 EFW 项目", str(REPO_ROOT), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if path:
            self.load_project_file(Path(path), remember=True, confirm_discard=False)

    def open_last_project(self) -> None:
        recent = load_recent_projects()
        if not recent:
            QMessageBox.information(self, "打开上次项目", "当前没有最近项目记录。请先打开或创建一个项目。")
            return
        path_text = recent[0]
        path = rel_or_abs(path_text)
        if not path.exists():
            fallback = REPO_ROOT / Path(path_text).name
            if fallback.exists():
                path = fallback
            else:
                remove_recent_project(path_text)
                self.refresh_recent_list()
                QMessageBox.warning(self, "打开上次项目", f"上次项目不存在，已从最近项目移除：\n{path_text}")
                return
        if not self._confirm_workspace_discard_changes():
            return
        self.load_project_file(path, remember=True, confirm_discard=False)

    def open_recent_project(self, item: QListWidgetItem) -> None:
        if not self._confirm_workspace_discard_changes():
            return
        path_text = item.text()
        path = rel_or_abs(path_text)
        if self.loading_recent_path == path:
            return
        self.loading_recent_path = path
        if not path.exists():
            # Try to locate the project in the repo root as a fallback
            fallback = REPO_ROOT / Path(path_text).name
            if fallback.exists():
                answer = QMessageBox.question(
                    self, "项目路径已移动",
                    f"项目文件原路径不存在：\n{display_path(path)}\n\n但在仓库根目录发现同名文件：\n{display_path(fallback)}\n\n是否使用新路径打开？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                yes = QMessageBox.StandardButton.Yes
                if answer == yes:
                    save_recent_projects([display_path(fallback) if p == path_text else p for p in load_recent_projects()])
                    self.refresh_recent_list()
                    self.load_project_file(fallback, remember=True, confirm_discard=False)
                    self.loading_recent_path = None
                    return
            remove_recent_project(path_text)
            self.refresh_recent_list()
            QMessageBox.warning(self, "最近项目不存在", f"找不到项目文件，已从最近项目移除：\n{display_path(path)}\n\n提示：如果项目已移动到其他位置，请使用「打开项目」重新加载。")
            self.loading_recent_path = None
            return
        self.load_project_file(path, remember=False, confirm_discard=False, auto_open_editor=True)
        self.loading_recent_path = None

    def load_project_file(self, path: Path, remember: bool = True, confirm_discard: bool = True, auto_open_editor: bool = False) -> None:
        if confirm_discard and not self._confirm_workspace_discard_changes():
            return
        if not path.exists():
            QMessageBox.warning(self, "项目不存在", f"找不到项目文件：\n{display_path(path)}")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("项目文件必须是 JSON 对象。")
        except Exception as exc:  # noqa: BLE001 - UI should show exact load failure.
            QMessageBox.warning(self, "项目无效", str(exc))
            return
        self.project_path = path
        merged = default_project()
        merged.update(data)
        merged = normalize_project_descriptor(merged, path)
        self.project = merged
        self.load_project_to_form()
        if remember:
            self.add_recent_project(path)
        
        # Auto-open editor if requested (e.g., double-click)
        if auto_open_editor:
            self.open_graph_editor()
            self.statusBar().showMessage(f"已加载并打开项目：{display_path(path)}", 7000)
        else:
            self.sync_embedded_editor_to_project()
            self.workspace_tabs.setCurrentIndex(0)

    def sync_embedded_editor_to_project(self) -> None:
        if self.embedded_editor is None:
            return
        graph_path = self.graph_path()
        if not graph_path.exists():
            self.statusBar().showMessage(f"项目 Graph 不存在：{display_path(graph_path)}", 7000)
            QMessageBox.warning(
                self,
                "Graph 不存在",
                f"当前项目引用的 Graph 文件不存在：\n{display_path(graph_path)}\n\n请检查项目文件中的 graph_path，或先通过项目向导重新创建 Graph。",
            )
            return
        self.embedded_editor.graph_path = graph_path
        self.embedded_editor.graph = json.loads(graph_path.read_text(encoding="utf-8"))
        self.embedded_editor.normalize_graph_runtime_state()
        self.embedded_editor.current_node_id = None
        self.embedded_editor._is_dirty = False
        self.embedded_editor.state_changed_callback = self.update_workspace_state
        project_out = self.output_dir()
        if project_out != REPO_ROOT / "application" / "generated_generic_embedded_app":
            self.embedded_editor._last_output_dir = project_out
        # Check autosave BEFORE refresh_all — refresh_all creates a fresh autosave via refresh_json_editor
        recovered = self.embedded_editor.check_autosave_recovery()
        if not recovered:
            self.embedded_editor.refresh_all()
        self.update_workspace_state()

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self.apply_form_to_project()
        self.save_embedded_graph()
        self.project_path.write_text(json.dumps(self.project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.add_recent_project(self.project_path)
        self._project_dirty = False
        self.update_workspace_state()
        self.statusBar().showMessage(f"已保存项目：{display_path(self.project_path)}", 5000)

    def save_embedded_graph(self) -> None:
        if self.embedded_editor is None:
            return
        graph_path = self.graph_path()
        if not graph_path:
            return
        self.embedded_editor.graph_path = graph_path
        self.embedded_editor._write_graph_to_disk(show_feedback=False)

    def save_project_as(self) -> None:
        default_name = f"{project_slug(str(self.project.get('name', 'efw_project')))}{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(self, "保存 EFW 项目", str(REPO_ROOT / default_name), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.save_project()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出 application 目录", str(REPO_ROOT / "application"))
        if path:
            self.output_edit.setText(display_path(Path(path)))

    def graph_path(self) -> Path:
        return rel_or_abs(str(self.project.get("graph_path", "")))

    def output_dir(self) -> Path:
        return rel_or_abs(self.output_edit.text().strip())

    def project_graph(self) -> dict[str, Any]:
        graph_path = self.graph_path()
        if self.embedded_editor is not None and self.embedded_editor.graph_path == graph_path:
            self.embedded_editor.apply_code_file(record_history=False)
            graph = copy.deepcopy(self.embedded_editor.graph)
        else:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        if not isinstance(graph, dict):
            raise ValueError("Graph JSON root must be an object")
        board = graph.setdefault("board", {})
        if not isinstance(board, dict):
            raise ValueError("graph.board must be an object")
        board["profile"] = self.project.get("board_profile", "generic-mock")
        return graph

    def validate_current_graph(self) -> bool:
        self.apply_form_to_project()
        graph_path = self.graph_path()
        try:
            graph = self.project_graph()
            validate_graph(graph)
        except Exception as exc:  # noqa: BLE001 - UI validation dialog should show exact validator message.
            QMessageBox.warning(self, "Graph 无效", str(exc))
            return False
        QMessageBox.information(self, "Graph 有效", f"Graph 校验通过：\n{display_path(graph_path)}\n\n下一步建议：\n1. 打开“项目装配”修正黄色/红色提示\n2. 再执行生成 application")
        return True

    def generate_application(self) -> None:
        self.apply_form_to_project()
        out_dir = self.output_dir()
        tmp_path: Path | None = None
        try:
            graph = self.project_graph()
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            preview = preview_application_files(tmp_path, out_dir)
            summary = "\n".join(f"{item['status']}: {item['path']}" for item in preview[:40])
            force = False
            if out_dir.exists() and any(out_dir.iterdir()):
                answer = QMessageBox.question(self, "Diff 预览 / 覆盖确认", f"输出目录已存在且非空，非生成文件会保留：\n{display_path(out_dir)}\n\n{summary}\n\n是否覆盖生成文件？")
                yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
                if answer != yes:
                    return
                force = True
            generate(tmp_path, out_dir, force=force)
        except Exception as exc:  # noqa: BLE001 - UI generation dialog should show exact generator message.
            QMessageBox.warning(self, "生成失败", str(exc))
            return
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        QMessageBox.information(self, "已生成", f"已生成 application：\n{display_path(out_dir)}\n\n下一步建议：\n1. 查看生成映射和文件树\n2. 在真实板卡工程中补 board_adapters\n3. 用 CMake/IDE 做一次编译验证")

    def quick_generate(self) -> None:
        """One-click validate and generate."""
        self.apply_form_to_project()
        
        # Step 1: Validate
        graph_path = self.graph_path()
        try:
            graph = self.project_graph()
            validate_graph(graph)
        except Exception as exc:
            QMessageBox.warning(self, "校验失败", f"Graph 校验失败，请先修复错误：\n\n{exc}")
            return
        
        # Step 2: Generate
        out_dir = self.output_dir()
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            
            # Auto-confirm overwrite for quick generate
            generate(tmp_path, out_dir, force=True)
            
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))
            return
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        
        QMessageBox.information(
            self,
            "一键生成完成",
            f"校验通过，已生成 application：\n{display_path(out_dir)}\n\n"
            f"下一步：\n"
            f"1. 在 board_adapters 中实现硬件操作\n"
            f"2. 用 Keil/STM32CubeIDE/ESP-IDF 编译验证"
        )

    def open_graph_editor(self) -> None:
        self.apply_form_to_project()
        graph_path = self.graph_path()
        if self.embedded_editor is None:
            self.embedded_editor = VisualEditorWindow(embedded=True)
            self.embedded_editor.state_changed_callback = self.update_workspace_state
            self.workspace_tabs.addTab(self.embedded_editor, "项目装配")
        self.sync_embedded_editor_to_project()
        self.workspace_tabs.setCurrentWidget(self.embedded_editor)

    def _ensure_embedded_editor(self) -> VisualEditorWindow | None:
        if self.embedded_editor is None:
            answer = QMessageBox.question(
                self,
                "打开项目装配",
                "当前还没有打开项目装配页。是否现在打开，以便显示资源/属性/输出面板？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            self.open_graph_editor()
        return self.embedded_editor

    def toggle_resource_dock(self) -> None:
        editor = self._ensure_embedded_editor()
        if editor is not None:
            editor.toggle_left_dock()

    def toggle_inspector_dock(self) -> None:
        editor = self._ensure_embedded_editor()
        if editor is not None:
            editor.toggle_right_dock()

    def toggle_output_dock(self) -> None:
        editor = self._ensure_embedded_editor()
        if editor is not None:
            editor.toggle_bottom_dock()

    def reset_editor_layout(self) -> None:
        editor = self._ensure_embedded_editor()
        if editor is not None:
            editor.reset_dock_layout()

    def show_shortcuts_dialog(self) -> None:
        if self.embedded_editor is not None:
            self.embedded_editor.show_shortcuts()
            return
        QMessageBox.information(
            self,
            "快捷键",
            "常用快捷键：\n"
            "Ctrl+S 保存全部/当前图\n"
            "Ctrl+Z 撤销\n"
            "Ctrl+Y 重做\n"
            "Ctrl+G 生成 application\n"
            "Ctrl+M 添加卡片\n"
            "Ctrl+Shift+B 创建分组区域\n"
            "Delete / Backspace 删除当前对象\n"
            "Tab 打开就地搜索插入框\n"
            "Ctrl+` 打开输出 / 日志区",
        )

    def show_debug_analysis(self) -> None:
        """Show the debug analysis panel."""
        # First ensure the embedded editor is open
        editor = self._ensure_embedded_editor()
        if editor is None:
            return
        
        # Switch to the debug tab in the bottom panel
        if hasattr(editor, 'bottom_tabs') and hasattr(editor, 'bottom_dock'):
            # Show the bottom dock if hidden
            if not editor.bottom_dock.isVisible():
                editor.bottom_dock.show()
            
            # Find and switch to the debug tab
            for i in range(editor.bottom_tabs.count()):
                if editor.bottom_tabs.tabText(i) == "运行分析":
                    editor.bottom_tabs.setCurrentIndex(i)
                    break
            
            # Refresh the analysis
            if hasattr(editor, 'refresh_debug_analysis'):
                editor.refresh_debug_analysis()
        
        # Switch to the assembly tab to show the editor
        self.workspace_tabs.setCurrentWidget(editor)

    def import_board_profile(self) -> None:
        """Import a board profile using chip wizard or JSON file."""
        # Ask user to choose import method
        choice = QMessageBox.question(
            self,
            "导入芯片配置",
            "请选择导入方式：\n\n"
            "• 是 - 从芯片数据库选择（推荐）\n"
            "• 否 - 从JSON文件导入",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            # Open chip selection wizard
            from studio.chip_wizard import ChipSelectionDialog
            dialog = ChipSelectionDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted if hasattr(QDialog, 'DialogCode') else dialog.exec_():
                chip_id = dialog.get_selected_chip_id()
                profile = dialog.get_selected_profile()
                if chip_id and profile:
                    # Add to board profiles
                    from studio.model import BOARD_PROFILES
                    BOARD_PROFILES[chip_id] = profile
                    
                    # Update combo box
                    self.board_edit.clear()
                    self.board_edit.addItems(list(BOARD_PROFILES))
                    self.board_edit.setCurrentText(chip_id)
                    
                    QMessageBox.information(
                        self,
                        "导入成功",
                        f"已从数据库导入芯片配置：\n{profile['label']}"
                    )
        else:
            # Import from JSON file
            path, _ = QFileDialog.getOpenFileName(
                self,
                "导入芯片配置 (Board Profile)",
                str(REPO_ROOT / "examples" / "board_profiles"),
                "所有支持的文件 (*.json .ioc sdkconfig);;JSON 文件 (*.json);;CubeMX 配置 (*.ioc);;ESP-IDF 配置 (sdkconfig);;所有文件 (*)"
            )
            if not path:
                return
            
            try:
                from studio.chip_database import detect_and_import
                from studio.chip_wizard import ChipImportResultDialog
                
                config, source = detect_and_import(Path(path))
                if not config:
                    QMessageBox.warning(
                        self,
                        "导入失败",
                        f"无法识别文件格式或提取配置信息。\n\n"
                        "支持的格式：\n"
                        "  • STM32CubeMX .ioc 文件\n"
                        "  • ESP-IDF sdkconfig 文件\n"
                        "  • 包含 board 配置的 JSON 文件"
                    )
                    return
                
                # Show import result dialog
                result_dialog = ChipImportResultDialog(config, source, self)
                if result_dialog.exec() == QDialog.DialogCode.Accepted if hasattr(QDialog, 'DialogCode') else result_dialog.exec_():
                    profile_name = result_dialog.get_profile_name()
                    profile = result_dialog.get_board_profile()
                    
                    # Add to board profiles
                    from studio.model import BOARD_PROFILES
                    BOARD_PROFILES[profile_name] = profile
                    
                    # Update combo box
                    self.board_edit.clear()
                    self.board_edit.addItems(list(BOARD_PROFILES))
                    self.board_edit.setCurrentText(profile_name)
                    
                    QMessageBox.information(
                        self,
                        "导入成功",
                        f"已导入芯片配置：{profile_name}"
                    )
            except Exception as exc:
                QMessageBox.warning(self, "导入失败", f"导入芯片配置失败：\n{exc}")

    def import_hardware_config(self) -> None:
        """Import a hardware configuration file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入硬件配置",
            str(REPO_ROOT / "examples"),
            "所有支持的文件 (*.json .ioc sdkconfig);;JSON 文件 (*.json);;CubeMX 配置 (*.ioc);;ESP-IDF 配置 (sdkconfig);;所有文件 (*)"
        )
        if not path:
            return
        
        try:
            from studio.chip_database import detect_and_import
            from studio.chip_wizard import ChipImportResultDialog
            
            file_path = Path(path)
            
            # Try auto-detect first
            config, source = detect_and_import(file_path)
            
            if config:
                # Show import result dialog
                result_dialog = ChipImportResultDialog(config, source, self)
                if result_dialog.exec() == QDialog.DialogCode.Accepted if hasattr(QDialog, 'DialogCode') else result_dialog.exec_():
                    profile_name = result_dialog.get_profile_name()
                    profile = result_dialog.get_board_profile()
                    
                    # Add to board profiles
                    from studio.model import BOARD_PROFILES
                    BOARD_PROFILES[profile_name] = profile
                    
                    # Update combo box
                    self.board_edit.clear()
                    self.board_edit.addItems(list(BOARD_PROFILES))
                    self.board_edit.setCurrentText(profile_name)
                    
                    QMessageBox.information(
                        self,
                        "导入成功",
                        f"已导入硬件配置：{profile_name}"
                    )
                    return
            
            # Fallback: try to parse as JSON with pin_plan
            if file_path.suffix.lower() == ".json":
                data = json.loads(file_path.read_text(encoding="utf-8"))
                
                # Check for pin_plan
                board = data.get("board", {})
                pin_plan = data.get("pin_plan") or (board.get("pin_plan") if isinstance(board, dict) else None)
                
                if isinstance(pin_plan, list):
                    # Update current project's pin plan
                    if "board" not in self.project:
                        self.project["board"] = {}
                    self.project["board"]["pin_plan"] = pin_plan
                    
                    QMessageBox.information(
                        self,
                        "导入成功",
                        f"已导入引脚配置，共 {len(pin_plan)} 个引脚定义"
                    )
                    return
            
            QMessageBox.warning(
                self,
                "格式不支持",
                "无法识别的硬件配置格式。\n\n"
                "支持的格式：\n"
                "  • STM32CubeMX .ioc 文件\n"
                "  • ESP-IDF sdkconfig 文件\n"
                "  • 包含引脚配置的 JSON 文件"
            )
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", f"导入硬件配置失败：\n{exc}")

    def export_board_profile(self) -> None:
        """Export current board profile to a JSON file."""
        current_profile = self.board_edit.currentText().strip()
        if not current_profile or current_profile not in BOARD_PROFILES:
            QMessageBox.warning(self, "导出失败", "请先选择一个有效的 Board Profile")
            return
        
        default_name = f"{current_profile}_profile.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出芯片配置",
            str(REPO_ROOT / "examples" / "board_profiles" / default_name),
            "JSON 文件 (*.json)"
        )
        if not path:
            return
        
        try:
            export_data = {current_profile: BOARD_PROFILES[current_profile]}
            Path(path).write_text(json.dumps(export_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            QMessageBox.information(self, "导出成功", f"已导出芯片配置到：\n{display_path(Path(path))}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", f"导出芯片配置失败：\n{exc}")

    def open_chip_wizard(self) -> None:
        """Open the chip selection wizard."""
        from studio.chip_wizard import ChipSelectionDialog
        dialog = ChipSelectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted if hasattr(QDialog, 'DialogCode') else dialog.exec_():
            chip_id = dialog.get_selected_chip_id()
            profile = dialog.get_selected_profile()
            if chip_id and profile:
                # Add to board profiles
                from studio.model import BOARD_PROFILES
                BOARD_PROFILES[chip_id] = profile
                
                # Update combo box
                self.board_edit.clear()
                self.board_edit.addItems(list(BOARD_PROFILES))
                self.board_edit.setCurrentText(chip_id)
                
                QMessageBox.information(
                    self,
                    "导入成功",
                    f"已从数据库导入芯片配置：\n{profile['label']}"
                )

    def show_about_dialog(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "关于 EFW 可视化项目工作台",
            "<h3>EFW 可视化项目工作台</h3>"
            "<p>版本: 1.0.0</p>"
            "<p>EFW (Embedded Framework) 是一个面向裸机和轻量RTOS的嵌入式C框架。</p>"
            "<p>本工具提供可视化的项目管理、蓝图编辑、代码生成功能。</p>"
            "<hr>"
            "<p><b>主要功能：</b></p>"
            "<ul>"
            "<li>可视化蓝图编辑器</li>"
            "<li>自动代码生成</li>"
            "<li>芯片配置管理</li>"
            "<li>运行流程分析</li>"
            "</ul>"
            "<hr>"
            "<p>项目地址: <a href='https://github.com/your-repo/efw'>GitHub</a></p>"
        )

    def closeEvent(self, event: Any) -> None:
        if self._confirm_workspace_discard_changes():
            event.accept()
        else:
            event.ignore()


def main() -> int:
    print("提示：推荐统一入口为 python3 tools/efw.py studio；当前脚本作为兼容入口继续启动工作台。", file=sys.stderr)
    if QApplication is None:
        print("未安装 PyQt。请安装 PyQt6 或 PyQt5 后再运行 python3 tools/efw.py studio。", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans CJK SC", 10))
    window = ProjectManagerWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
