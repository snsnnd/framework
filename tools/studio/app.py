#!/usr/bin/env python3
"""Single startup entry for the EFW visual workbench.

Run this script instead of launching the project manager or graph editor
separately.  The workbench embeds the graph editor inside the project manager so
project creation, graph editing, validation, and generation share one UI.
"""

from __future__ import annotations

import sys

from studio.manager import QApplication, QFont, ProjectManagerWindow


def main() -> int:
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
