#!/usr/bin/env python3
"""Single startup entry for the EFW visual workbench.

Run this script instead of launching the project manager or graph editor
separately.  The workbench embeds the graph editor inside the project manager so
project creation, graph editing, validation, and generation share one UI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from efw_project_manager import QApplication, QFont, ProjectManagerWindow  # noqa: E402


def main() -> int:
    if QApplication is None:
        print("未安装 PyQt。请安装 PyQt6 或 PyQt5 后再运行 tools/efw_studio.py。", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans CJK SC", 10))
    window = ProjectManagerWindow()
    window.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
