"""Command-line interface for EFW code generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import generate, preview_application_files


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an EFW application from a graph JSON file.")
    parser.add_argument("graph", type=Path, help="path to graph JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output application directory")
    parser.add_argument("--force", action="store_true", help="replace output directory if it already exists")
    parser.add_argument("--dry-run", action="store_true", help="preview what would be generated without writing files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.dry_run:
            preview = preview_application_files(args.graph, args.output)
            if not preview:
                print(f"efw-codegen: no files would be generated for {args.graph}")
                return 0
            print(f"Dry-run preview for: {args.graph} → {args.output}")
            print(f"{'Status':<22} {'Path'}")
            print("-" * 60)
            for item in preview:
                status = item.get("status", "unknown")
                path = item.get("path", "?")
                sha_info = ""
                if item.get("new_sha"):
                    sha_info = f"  sha: {item.get('old_sha', 'new')}→{item['new_sha']}"
                protection = f"  ({item['protected_by']})" if item.get("protected_by") else ""
                print(f"{status:<22} {path}{sha_info}{protection}")
            return 0
        generate(args.graph, args.output, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"efw-codegen: {exc}", file=sys.stderr)
        return 1
    print(f"generated EFW application: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
