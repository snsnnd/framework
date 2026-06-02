#!/usr/bin/env python3
"""PyQt project manager for EFW visual-codegen projects.

The visual editor edits one graph at a time. This project manager adds a thin
workspace layer around that graph: it remembers the graph file, output
application directory, target board profile, and notes so users can manage a
small embedded project without repeatedly typing paths.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QComboBox,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QComboBox,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTabWidget,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QApplication = None
    QFileDialog = QInputDialog = QMessageBox = None
    QFont = object
    QComboBox = QFormLayout = QHBoxLayout = QLabel = QLineEdit = QListWidget = QListWidgetItem = object
    QMainWindow = QPushButton = QPlainTextEdit = QSplitter = QTabWidget = QToolBar = QVBoxLayout = QWidget = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[2]

from codegen import generate, preview_application_files
from codegen.validate import validate_graph
from studio.editor import VisualEditorWindow
from studio.model import BOARD_PROFILES

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
                "name": "app_module",
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
        self.setStyleSheet(WORKBENCH_STYLESHEET)
        self._build_ui()
        self.refresh_recent_list()
        self.load_project_to_form()

    def _build_ui(self) -> None:
        toolbar = QToolBar("项目工具栏")
        self.addToolBar(toolbar)
        toolbar.addAction("新建", self.new_project)
        toolbar.addAction("项目创建向导", self.project_wizard)
        toolbar.addAction("打开", self.open_project)
        toolbar.addAction("保存项目", self.save_project)
        toolbar.addAction("项目另存为", self.save_project_as)
        toolbar.addAction("实时校验", self.validate_current_graph)
        toolbar.addAction("生成", self.generate_application)
        toolbar.addAction("打开当前项目", self.open_graph_editor)

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

        buttons = QHBoxLayout()
        for text, callback in [
            ("实时校验", self.validate_current_graph),
            ("生成 application", self.generate_application),
            ("打开当前项目", self.open_graph_editor),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        root.addLayout(buttons)
        splitter.addWidget(editor)
        splitter.setChildrenCollapsible(True)
        splitter.setSizes([220, 680])

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

    def new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "新建 EFW 项目", "项目名", text="new_efw_project")
        if not ok or not name.strip():
            return
        board = self.board_edit.currentText().strip() or "generic-mock"
        output_dir = f"application/generated_{project_slug(name)}"
        self.create_project_files(name.strip(), blank_graph(name.strip(), board), output_dir, board)

    def project_wizard(self) -> None:
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
        default_path = REPO_ROOT / ".efw_projects" / slug / f"{slug}{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(self, "创建 EFW 项目", str(default_path), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if not path:
            return
        project_path = Path(path)
        project_dir = project_path.parent
        graph_path = project_dir / "graph.json"
        if graph_path.exists() or project_path.exists():
            answer = QMessageBox.question(self, "覆盖确认", f"项目文件或 graph.json 已存在：\n{display_path(project_dir)}\n\n是否覆盖？")
            yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
            if answer != yes:
                return
        project_dir.mkdir(parents=True, exist_ok=True)
        graph.setdefault("project", {})["name"] = name
        graph.setdefault("board", {})["profile"] = board
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.project_path = project_path
        self.project = {
            "kind": "efw.project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": name,
            "description": f"{name} 的 EFW Studio 项目描述文件。",
            "graph_path": display_path(graph_path),
            "output_dir": output_dir,
            "board_profile": board,
            "notes": "由项目创建向导生成。建议先打开项目装配检查卡片、Board Profile 和 Pin Planner，再生成 application/。",
            "workflow": default_project()["workflow"],
        }
        self.save_project()
        self.load_project_to_form()

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 EFW 项目", str(REPO_ROOT), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if path:
            self.load_project_file(Path(path), remember=True)

    def open_recent_project(self, item: QListWidgetItem) -> None:
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
                    self.load_project_file(fallback, remember=True)
                    self.loading_recent_path = None
                    return
            remove_recent_project(path_text)
            self.refresh_recent_list()
            QMessageBox.warning(self, "最近项目不存在", f"找不到项目文件，已从最近项目移除：\n{display_path(path)}\n\n提示：如果项目已移动到其他位置，请使用「打开项目」重新加载。")
            self.loading_recent_path = None
            return
        self.load_project_file(path, remember=False)
        self.loading_recent_path = None

    def load_project_file(self, path: Path, remember: bool = True) -> None:
        if self.embedded_editor is not None and not self.embedded_editor._confirm_discard_changes():
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
        self.sync_embedded_editor_to_project()
        self.workspace_tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"已加载项目：{display_path(path)}。点击“打开当前项目”进入装配。", 7000)

    def sync_embedded_editor_to_project(self) -> None:
        if self.embedded_editor is None:
            return
        graph_path = self.graph_path()
        if not graph_path.exists():
            return
        self.embedded_editor.graph_path = graph_path
        self.embedded_editor.graph = json.loads(graph_path.read_text(encoding="utf-8"))
        self.embedded_editor.current_node_id = None
        self.embedded_editor._is_dirty = False
        project_out = self.output_dir()
        if project_out != REPO_ROOT / "application" / "generated_generic_embedded_app":
            self.embedded_editor._last_output_dir = project_out
        # Check autosave BEFORE refresh_all — refresh_all creates a fresh autosave via refresh_json_editor
        recovered = self.embedded_editor.check_autosave_recovery()
        if not recovered:
            self.embedded_editor.refresh_all()

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self.save_embedded_graph()
        self.apply_form_to_project()
        self.project_path.write_text(json.dumps(self.project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.add_recent_project(self.project_path)
        self.statusBar().showMessage(f"已保存项目：{display_path(self.project_path)}", 5000)

    def save_embedded_graph(self) -> None:
        if self.embedded_editor is None:
            return
        graph_path = self.graph_path()
        if not graph_path:
            return
        self.embedded_editor.graph_path = graph_path
        self.embedded_editor.save_graph()

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
        QMessageBox.information(self, "Graph 有效", f"Graph 校验通过：\n{display_path(graph_path)}")
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
        QMessageBox.information(self, "已生成", f"已生成 application:\n{display_path(out_dir)}")

    def open_graph_editor(self) -> None:
        self.apply_form_to_project()
        graph_path = self.graph_path()
        if self.embedded_editor is None:
            self.embedded_editor = VisualEditorWindow(embedded=True)
            self.workspace_tabs.addTab(self.embedded_editor, "项目装配")
        self.sync_embedded_editor_to_project()
        self.workspace_tabs.setCurrentWidget(self.embedded_editor)

    def closeEvent(self, event: Any) -> None:
        if self.embedded_editor is None or self.embedded_editor._confirm_discard_changes():
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
