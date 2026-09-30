"""Non-UI project operations shared by CLI and Studio."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Iterator

try:
    from codegen import generate, preview_application_files
    from codegen.debug import debug_graph
    from codegen.validate import validate_graph
except ImportError:  # Allow importing tools.api from the repository root.
    from tools.codegen import generate, preview_application_files  # type: ignore[no-redef]
    from tools.codegen.debug import debug_graph  # type: ignore[no-redef]
    from tools.codegen.validate import validate_graph  # type: ignore[no-redef]


@contextlib.contextmanager
def graph_as_temp_file(graph: dict[str, Any]) -> Iterator[Path]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(graph, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_graph_data(graph: dict[str, Any]) -> dict[str, Any]:
    return validate_graph(graph)


def preview_graph_generation(graph: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    with graph_as_temp_file(graph) as graph_path:
        return preview_application_files(graph_path, output_dir)


def generate_graph_application(graph: dict[str, Any], output_dir: Path, force: bool = False) -> None:
    with graph_as_temp_file(graph) as graph_path:
        generate(graph_path, output_dir, force=force)


def analyze_graph_runtime(graph: dict[str, Any], sections: list[str] | None = None) -> tuple[int, str, str]:
    with graph_as_temp_file(graph) as graph_path:
        return analyze_graph_runtime_file(graph_path, sections)


def analyze_graph_runtime_file(graph_path: Path, sections: list[str] | None = None) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = debug_graph(graph_path, sections)
    return result, stdout.getvalue(), stderr.getvalue()
