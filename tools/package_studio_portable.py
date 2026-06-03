#!/usr/bin/env python3
"""Build a portable Windows EFW Studio directory.

Usage:
  python3 tools/package_studio_portable.py
"""

from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = REPO_ROOT / "dist"
PACKAGE_ROOT = DIST_ROOT / "efw-studio-portable"
PACKAGING_ROOT = REPO_ROOT / "packaging"
WINDOWS_VENV = REPO_ROOT / ".venv"
LEGACY_ARTIFACTS = [
    DIST_ROOT / "efw-studio-tool",
    DIST_ROOT / "efw-studio-tool.zip",
]


INCLUDE_PATHS = [
    ".venv",
    "tools",
    "examples/graphs",
    "examples/projects",
    "examples/board_profiles",
    "include",
    "src",
    "docs/codegen.md",
    "docs/environment.md",
    "用户文档",
    "README.md",
    "CMakeLists.txt",
]


def clean_output() -> None:
    if PACKAGE_ROOT.exists():
        shutil.rmtree(PACKAGE_ROOT)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for path in LEGACY_ARTIFACTS:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()


def copy_path(rel_path: str) -> None:
    src = REPO_ROOT / rel_path
    dest = PACKAGE_ROOT / rel_path
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".efw_autosave_*.json",
                ".efw_studio_autosave.json",
                ".efw_projects",
                ".claude",
                "dist",
                "build",
            ),
        )
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_launchers() -> None:
    (PACKAGE_ROOT / "start_studio.bat").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set ROOT=%~dp0\r\n"
        "\"%ROOT%.venv\\Scripts\\python.exe\" \"%ROOT%tools\\efw.py\" studio\r\n"
        "if errorlevel 1 pause\r\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "start_codegen_demo.bat").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set ROOT=%~dp0\r\n"
        "\"%ROOT%.venv\\Scripts\\python.exe\" \"%ROOT%tools\\efw.py\" codegen \"%ROOT%examples\\graphs\\generic_embedded_app.json\" -o \"%ROOT%application\\generated_generic_embedded_app\" --force\r\n"
        "pause\r\n",
        encoding="utf-8",
    )


def copy_package_readme() -> None:
    shutil.copy2(PACKAGING_ROOT / "studio-portable-README.md", PACKAGE_ROOT / "PACKAGE_README.md")


def zip_output() -> Path:
    zip_path = DIST_ROOT / "efw-studio-portable.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE_ROOT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(DIST_ROOT))
    return zip_path


def main() -> int:
    if not WINDOWS_VENV.exists() or not (WINDOWS_VENV / "Scripts" / "python.exe").exists():
        raise SystemExit("Missing Windows .venv with Scripts/python.exe; cannot build portable Studio package.")
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    clean_output()
    for rel_path in INCLUDE_PATHS:
        copy_path(rel_path)
    copy_package_readme()
    write_launchers()
    zip_path = zip_output()
    print("Generated portable Studio package:")
    print(f"- {PACKAGE_ROOT.relative_to(REPO_ROOT)}")
    print(f"- {zip_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
