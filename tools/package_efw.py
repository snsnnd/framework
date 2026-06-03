#!/usr/bin/env python3
"""Build distributable EFW package archives.

Usage:
  python3 tools/package_efw.py
"""

from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = REPO_ROOT / "dist"
PACKAGING_ROOT = REPO_ROOT / "packaging"


PACKAGE_DEFS = {
    "efw-runtime-sdk": {
        "root_dir_name": "efw-runtime-sdk",
        "paths": [
            "include",
            "src",
            "CMakeLists.txt",
            "README.md",
            "docs/api_reference.md",
            "docs/design.md",
        ],
        "extra_files": {
            "PACKAGE_README.md": PACKAGING_ROOT / "runtime-sdk-README.md",
        },
    },
    "efw-studio-tool": {
        "root_dir_name": "efw-studio-tool",
        "paths": [
            "tools",
            "examples/graphs",
            "examples/projects",
            "examples/board_profiles",
            "include",
            "src",
            "CMakeLists.txt",
            "README.md",
            "docs/codegen.md",
            "docs/environment.md",
        ],
        "extra_files": {
            "PACKAGE_README.md": PACKAGING_ROOT / "studio-tool-README.md",
        },
    },
}


def clean_dist() -> None:
    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)


def copy_path(src_rel: str, dest_root: Path) -> None:
    src = REPO_ROOT / src_rel
    dest = dest_root / src_rel
    if src.is_dir():
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".efw_autosave_*.json",
            ".efw_studio_autosave.json",
            ".efw_projects",
            ".claude",
            ".venv",
            "build",
            "dist",
        ))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def add_extra_files(extra_files: dict[str, Path], dest_root: Path) -> None:
    for dest_rel, src in extra_files.items():
        target = dest_root / dest_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def make_zip(source_dir: Path, zip_path: Path) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir.parent))


def build_package(name: str, spec: dict[str, object]) -> None:
    package_root = DIST_ROOT / str(spec["root_dir_name"])
    package_root.mkdir(parents=True, exist_ok=True)
    for rel in spec["paths"]:
        copy_path(str(rel), package_root)
    add_extra_files(spec["extra_files"], package_root)
    make_zip(package_root, DIST_ROOT / f"{name}.zip")


def main() -> int:
    clean_dist()
    for name, spec in PACKAGE_DEFS.items():
        build_package(name, spec)
    print("Generated packages:")
    for path in sorted(DIST_ROOT.iterdir()):
        print(f"- {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
