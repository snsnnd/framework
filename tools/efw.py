#!/usr/bin/env python3
"""Unified entry point for EFW tools.

Usage:
  python3 tools/efw.py studio
  python3 tools/efw.py codegen examples/graphs/generic_embedded_app.json -o application/generated_app --force

Running without a subcommand starts Studio.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    command = args[0] if args else "studio"
    rest = args[1:] if args else []

    if command in {"studio", "gui"}:
        from studio.app import main as studio_main

        return studio_main()
    if command in {"codegen", "generate"}:
        from codegen.cli import main as codegen_main

        return codegen_main(rest)
    if command in {"-h", "--help", "help"}:
        print(__doc__.strip())
        return 0
    print(f"unknown EFW tool command: {command}", file=sys.stderr)
    print("Run `python3 tools/efw.py --help` for usage.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
