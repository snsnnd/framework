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
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
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
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QApplication = None
    QMainWindow = object
    QT_LIB = "missing"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from efw_codegen import generate, validate_graph  # noqa: E402
from efw_visual_editor import VisualEditorWindow  # noqa: E402

WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { background: #101820; color: #e8f0f2; font-family: "Noto Sans CJK SC", "Microsoft YaHei", "WenQuanYi Micro Hei", "DejaVu Sans"; }
QToolBar { background: #162532; border-bottom: 1px solid #29465c; spacing: 6px; }
QToolButton, QPushButton {
    background: #1f3a4d;
    color: #f5fbff;
    border: 1px solid #3f6b82;
    border-radius: 5px;
    padding: 5px 9px;
}
QToolButton:hover, QPushButton:hover { background: #28516a; border-color: #5fa8c8; }
QListWidget, QPlainTextEdit, QLineEdit {
    background: #0d141b;
    color: #e8f0f2;
    border: 1px solid #29465c;
    selection-background-color: #2d6f8f;
}
QLabel { color: #e8f0f2; }
"""

PROJECT_SCHEMA_VERSION = 1
PROJECT_SUFFIX = ".efw_project.json"
RECENT_FILE = REPO_ROOT / ".efw_projects" / "recent.json"


def default_project() -> dict[str, Any]:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": "generic_embedded_app",
        "graph_path": "examples/graphs/generic_embedded_app.json",
        "output_dir": "application/generated_generic_embedded_app",
        "board_profile": "generic-mock",
        "notes": "Use the graph editor to edit cards/code, then generate application/. Put board-specific glue in graph.board_adapters.",
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
    return [str(item) for item in data if isinstance(item, str)]


def save_recent_projects(paths: list[str]) -> None:
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    unique: list[str] = []
    for item in paths:
        if item not in unique:
            unique.append(item)
    RECENT_FILE.write_text(json.dumps(unique[:20], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ProjectManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"EFW 可视化项目工作台 ({QT_LIB})")
        self.resize(1120, 680)
        self.project_path: Path | None = None
        self.project = default_project()
        self.graph_editor_windows: list[VisualEditorWindow] = []
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
        toolbar.addAction("保存", self.save_project)
        toolbar.addAction("另存为", self.save_project_as)
        toolbar.addAction("实时校验", self.validate_current_graph)
        toolbar.addAction("生成", self.generate_application)
        toolbar.addAction("打开蓝图编辑", self.open_graph_editor)

        splitter = QSplitter()
        self.setCentralWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("最近项目"))
        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self.open_recent_project)
        left_layout.addWidget(self.recent_list)
        splitter.addWidget(left)

        editor = QWidget()
        root = QVBoxLayout(editor)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.graph_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.board_edit = QLineEdit()
        form.addRow("项目名", self.name_edit)
        form.addRow("Graph JSON", self._path_row(self.graph_edit, self.choose_graph_path))
        form.addRow("输出 application", self._path_row(self.output_edit, self.choose_output_dir))
        form.addRow("Board Profile", self.board_edit)
        root.addLayout(form)
        root.addWidget(QLabel("说明 / 交接清单"))
        self.notes_edit = QPlainTextEdit()
        root.addWidget(self.notes_edit)

        buttons = QHBoxLayout()
        for text, callback in [
            ("实时校验", self.validate_current_graph),
            ("生成 application", self.generate_application),
            ("打开蓝图编辑", self.open_graph_editor),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        root.addLayout(buttons)
        splitter.addWidget(editor)
        splitter.setSizes([280, 840])

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
        self.name_edit.setText(str(self.project.get("name", "")))
        self.graph_edit.setText(str(self.project.get("graph_path", "")))
        self.output_edit.setText(str(self.project.get("output_dir", "")))
        self.board_edit.setText(str(self.project.get("board_profile", "")))
        self.notes_edit.setPlainText(str(self.project.get("notes", "")))

    def apply_form_to_project(self) -> None:
        self.project = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": self.name_edit.text().strip() or "generated_app",
            "graph_path": self.graph_edit.text().strip(),
            "output_dir": self.output_edit.text().strip(),
            "board_profile": self.board_edit.text().strip() or "generic-mock",
            "notes": self.notes_edit.toPlainText(),
        }

    def refresh_recent_list(self) -> None:
        self.recent_list.clear()
        for path in load_recent_projects():
            QListWidgetItem(path, self.recent_list)

    def add_recent_project(self, path: Path) -> None:
        current = load_recent_projects()
        text = display_path(path)
        save_recent_projects([text] + [item for item in current if item != text])
        self.refresh_recent_list()

    def new_project(self) -> None:
        self.project_path = None
        self.project = default_project()
        self.load_project_to_form()

    def project_wizard(self) -> None:
        templates = {
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
            output_dir = f"application/generated_{custom_name}"
        self.project_path = None
        self.project = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": name,
            "graph_path": graph_path,
            "output_dir": output_dir,
            "board_profile": board,
            "notes": "由项目创建向导生成。建议先打开蓝图编辑器检查卡片、Board Profile 和 Pin Planner，再生成 application/。",
        }
        self.load_project_to_form()

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 EFW 项目", str(REPO_ROOT), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if path:
            self.load_project_file(Path(path))

    def open_recent_project(self, item: QListWidgetItem) -> None:
        self.load_project_file(rel_or_abs(item.text()))

    def load_project_file(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            QMessageBox.warning(self, "项目无效", "项目文件必须是 JSON 对象。")
            return
        self.project_path = path
        merged = default_project()
        merged.update(data)
        self.project = merged
        self.load_project_to_form()
        self.add_recent_project(path)

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self.apply_form_to_project()
        self.project_path.write_text(json.dumps(self.project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.add_recent_project(self.project_path)

    def save_project_as(self) -> None:
        default_name = f"{self.name_edit.text().strip() or 'efw_project'}{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(self, "保存 EFW 项目", str(REPO_ROOT / default_name), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.save_project()

    def choose_graph_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Graph JSON", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if path:
            self.graph_edit.setText(display_path(Path(path)))

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出 application 目录", str(REPO_ROOT / "application"))
        if path:
            self.output_edit.setText(display_path(Path(path)))

    def graph_path(self) -> Path:
        return rel_or_abs(self.graph_edit.text().strip())

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
        graph_path = self.graph_path()
        out_dir = self.output_dir()
        try:
            graph = self.project_graph()
            force = False
            if out_dir.exists() and any(out_dir.iterdir()):
                answer = QMessageBox.question(self, "覆盖确认", f"输出目录已存在且非空：\n{display_path(out_dir)}\n是否清空并重新生成？")
                yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
                if answer != yes:
                    return
                force = True
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(graph, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            try:
                generate(tmp_path, out_dir, force=force)
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - UI generation dialog should show exact generator message.
            QMessageBox.warning(self, "生成失败", str(exc))
            return
        QMessageBox.information(self, "已生成", f"已生成 application:\n{display_path(out_dir)}")

    def open_graph_editor(self) -> None:
        graph_path = self.graph_path()
        window = VisualEditorWindow()
        if graph_path.exists():
            window.graph_path = graph_path
            window.graph = json.loads(graph_path.read_text(encoding="utf-8"))
            window.current_node_id = None
            window.refresh_all()
        self.graph_editor_windows.append(window)
        window.show()


def main() -> int:
    if QApplication is None:
        print("未安装 PyQt。请安装 PyQt6 或 PyQt5 后再运行 tools/efw_project_manager.py。", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans CJK SC", 10))
    window = ProjectManagerWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
