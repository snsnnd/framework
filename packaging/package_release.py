#!/usr/bin/env python3
"""Build the final user-facing EFW release packages.

Usage:
  python3 tools/package_release.py

This command generates:
  - dist/efw-runtime-sdk.zip
  - dist/efw-studio-portable.zip
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(script_name: str) -> None:
    script_path = REPO_ROOT / "tools" / script_name
    subprocess.run([sys.executable, str(script_path)], cwd=REPO_ROOT, check=True)


def main() -> int:
    run("package_efw.py")
    run("package_studio_portable.py")
    print("Final release packages are ready:")
    print("- dist/efw-runtime-sdk.zip")
    print("- dist/efw-studio-portable.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
