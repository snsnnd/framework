"""PyInstaller 入口：与 `python -m studio_core.server` 等价，只是需要一个脚本文件。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio_core.server import main  # noqa: E402

if __name__ == "__main__":
    main()
