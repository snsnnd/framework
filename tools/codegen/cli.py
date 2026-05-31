"""Command-line interface for EFW code generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import generate


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an EFW application from a graph JSON file.")
    parser.add_argument("graph", type=Path, help="path to graph JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output application directory")
    parser.add_argument("--force", action="store_true", help="replace output directory if it already exists")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        generate(args.graph, args.output, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"efw-codegen: {exc}", file=sys.stderr)
        return 1
    print(f"generated EFW application: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
