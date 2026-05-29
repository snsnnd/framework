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
from pathlib import Path
from typing import Any

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
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
    from PyQt5.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
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
        self.setWindowTitle(f"EFW Project Manager ({QT_LIB})")
        self.resize(1120, 680)
        self.project_path: Path | None = None
        self.project = default_project()
        self.graph_editor_windows: list[VisualEditorWindow] = []
        self._build_ui()
        self.refresh_recent_list()
        self.load_project_to_form()

    def _build_ui(self) -> None:
        toolbar = QToolBar("Project")
        self.addToolBar(toolbar)
        toolbar.addAction("New", self.new_project)
        toolbar.addAction("Open", self.open_project)
        toolbar.addAction("Save", self.save_project)
        toolbar.addAction("Save As", self.save_project_as)
        toolbar.addAction("Validate Graph", self.validate_current_graph)
        toolbar.addAction("Generate", self.generate_application)
        toolbar.addAction("Open Graph Editor", self.open_graph_editor)

        splitter = QSplitter()
        self.setCentralWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Recent Projects"))
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
        form.addRow("Project name", self.name_edit)
        form.addRow("Graph JSON", self._path_row(self.graph_edit, self.choose_graph_path))
        form.addRow("Output application", self._path_row(self.output_edit, self.choose_output_dir))
        form.addRow("Board profile", self.board_edit)
        root.addLayout(form)
        root.addWidget(QLabel("Notes / handoff checklist"))
        self.notes_edit = QPlainTextEdit()
        root.addWidget(self.notes_edit)

        buttons = QHBoxLayout()
        for text, callback in [
            ("Validate", self.validate_current_graph),
            ("Generate Application", self.generate_application),
            ("Open Graph Editor", self.open_graph_editor),
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
        button = QPushButton("Browse")
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

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open EFW project", str(REPO_ROOT), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if path:
            self.load_project_file(Path(path))

    def open_recent_project(self, item: QListWidgetItem) -> None:
        self.load_project_file(rel_or_abs(item.text()))

    def load_project_file(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid project", "Project file must contain a JSON object.")
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
        path, _ = QFileDialog.getSaveFileName(self, "Save EFW project", str(REPO_ROOT / default_name), f"EFW Project (*{PROJECT_SUFFIX});;JSON (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.save_project()

    def choose_graph_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select graph JSON", str(REPO_ROOT / "examples" / "graphs"), "JSON (*.json)")
        if path:
            self.graph_edit.setText(display_path(Path(path)))

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output application directory", str(REPO_ROOT / "application"))
        if path:
            self.output_edit.setText(display_path(Path(path)))

    def graph_path(self) -> Path:
        return rel_or_abs(self.graph_edit.text().strip())

    def output_dir(self) -> Path:
        return rel_or_abs(self.output_edit.text().strip())

    def validate_current_graph(self) -> bool:
        self.apply_form_to_project()
        graph_path = self.graph_path()
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        try:
            validate_graph(graph)
        except Exception as exc:  # noqa: BLE001 - UI validation dialog should show exact validator message.
            QMessageBox.warning(self, "Graph invalid", str(exc))
            return False
        QMessageBox.information(self, "Graph valid", f"Graph is valid:\n{display_path(graph_path)}")
        return True

    def generate_application(self) -> None:
        self.apply_form_to_project()
        graph_path = self.graph_path()
        out_dir = self.output_dir()
        try:
            generate(graph_path, out_dir, force=True)
        except Exception as exc:  # noqa: BLE001 - UI generation dialog should show exact generator message.
            QMessageBox.warning(self, "Generate failed", str(exc))
            return
        QMessageBox.information(self, "Generated", f"Generated application:\n{display_path(out_dir)}")

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
        print("PyQt is not installed. Install PyQt6 or PyQt5, then run tools/efw_project_manager.py.", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    window = ProjectManagerWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
