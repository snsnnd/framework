#!/usr/bin/env python3
"""EFW unified tool entry point.

Usage:
  python3 tools/efw.py <command> [options]

Commands:
  studio      Launch the visual workbench (default)
  codegen     Generate application code from a graph JSON
  package     Build distributable packages
  test        Run framework tests
  build       Build framework library
  help        Show this help message

Run `python3 tools/efw.py <command> --help` for command-specific help.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_ROOT.parent

COMMANDS = {
    "studio": "Launch the visual workbench",
    "codegen": "Generate application code from a graph JSON",
    "debug": "Analyze and trace runtime flow of a graph",
    "package": "Build distributable packages (sdk/portable/all)",
    "test": "Run framework tests",
    "build": "Build framework library",
    "help": "Show this help message",
}

ALIASES = {
    "gui": "studio",
    "generate": "codegen",
    "pack": "package",
    "trace": "debug",
}


def print_help() -> None:
    """Print main help with all available commands."""
    print(__doc__.strip())
    print("\nAvailable commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:<12} {desc}")
    print(f"\nAliases: {', '.join(f'{a}->{b}' for a, b in ALIASES.items())}")
    print("\nExamples:")
    print("  python3 tools/efw.py studio")
    print("  python3 tools/efw.py codegen examples/graphs/generic_embedded_app.json -o app/ --force")
    print("  python3 tools/efw.py debug examples/graphs/generic_embedded_app.json")
    print("  python3 tools/efw.py debug examples/graphs/generic_embedded_app.json --sections init,dataflow,state")
    print("  python3 tools/efw.py package sdk")
    print("  python3 tools/efw.py package portable")
    print("  python3 tools/efw.py package all")
    print("  python3 tools/efw.py test")
    print("  python3 tools/efw.py build")


def print_command_help(command: str) -> None:
    """Print help for a specific command."""
    helps = {
        "studio": """Usage: python3 tools/efw.py studio

Launch the EFW visual workbench for graph editing, validation, and code generation.
Requires PyQt6 or PyQt5.""",
        "codegen": """Usage: python3 tools/efw.py codegen <graph.json> -o <output_dir> [options]

Generate an EFW application from a graph JSON file.

Options:
  -o, --output    Output application directory (required)
  --force         Replace output directory if it exists
  --dry-run       Preview what would be generated without writing files

Example:
  python3 tools/efw.py codegen examples/graphs/generic_embedded_app.json -o application/generated_app --force""",
        "debug": """Usage: python3 tools/efw.py debug <graph.json> [options]

Analyze and trace the runtime flow of an EFW graph.
Shows initialization order, dataflow pipelines, scheduler tasks,
state machine transitions, and event pub/sub topology.

Options:
  --sections      Comma-separated list of sections to show
  --list          List available debug sections

Sections:
  info            Project overview and node statistics
  init            Initialization and registration order
  dataflow        Dataflow pipeline paths
  scheduler       Scheduler task timeline
  state           State machine definitions and transitions
  events          Event pub/sub topology
  loop            Runtime loop execution order
  linefollower    Line follower flow configuration
  all             Show all sections (default)

Examples:
  python3 tools/efw.py debug examples/graphs/generic_embedded_app.json
  python3 tools/efw.py debug examples/graphs/generic_embedded_app.json --sections init,dataflow,state
  python3 tools/efw.py debug --list""",
        "package": """Usage: python3 tools/efw.py package <target>

Build distributable packages.

Targets:
  sdk         Build EFW Runtime SDK (for embedded developers)
  portable    Build EFW Studio Portable (for end users)
  all         Build both packages (default)

Examples:
  python3 tools/efw.py package sdk
  python3 tools/efw.py package portable
  python3 tools/efw.py package all""",
        "test": """Usage: python3 tools/efw.py test [options]

Run framework tests.

Options:
  --verbose, -v    Show detailed test output
  --build          Build before running tests

Examples:
  python3 tools/efw.py test
  python3 tools/efw.py test --verbose""",
        "build": """Usage: python3 tools/efw.py build [options]

Build the EFW framework library.

Options:
  --clean          Clean build directory before building
  --apps           Also build application examples
  --tests          Also build tests (default: on)

Examples:
  python3 tools/efw.py build
  python3 tools/efw.py build --clean --apps""",
    }
    print(helps.get(command, f"No help available for '{command}'."))


def cmd_studio() -> int:
    """Launch the visual workbench."""
    try:
        from studio.app import main as studio_main
        return studio_main()
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("PyQt is required. Install with: pip install PyQt6", file=sys.stderr)
        return 1


def cmd_codegen(argv: list[str]) -> int:
    """Run code generation."""
    from codegen.cli import main as codegen_main
    return codegen_main(argv)


def cmd_package(argv: list[str]) -> int:
    """Build distributable packages."""
    target = argv[0] if argv else "all"
    
    if target in {"--help", "-h", "help"}:
        print_command_help("package")
        return 0
    
    valid_targets = {"sdk", "portable", "all"}
    if target not in valid_targets:
        print(f"Error: Unknown package target '{target}'", file=sys.stderr)
        print(f"Valid targets: {', '.join(sorted(valid_targets))}", file=sys.stderr)
        return 1
    
    scripts = {
        "sdk": TOOLS_ROOT / "package_efw.py",
        "portable": TOOLS_ROOT / "package_studio_portable.py",
        "all": TOOLS_ROOT / "package_release.py",
    }
    
    script = scripts[target]
    if target == "all":
        print("Building all packages...")
    else:
        print(f"Building {target} package...")
    
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=False,
    )
    return result.returncode


def cmd_test(argv: list[str]) -> int:
    """Run framework tests."""
    verbose = "--verbose" in argv or "-v" in argv
    do_build = "--build" in argv
    
    build_dir = REPO_ROOT / "build_test"
    build_dir.mkdir(exist_ok=True)
    
    if do_build:
        print("Building framework...")
        result = subprocess.run(
            ["cmake", "-S", str(REPO_ROOT), "-B", str(build_dir), 
             "-DEFW_BUILD_TESTS=ON", "-DEFW_BUILD_APPLICATIONS=OFF"],
            cwd=REPO_ROOT,
            capture_output=not verbose,
        )
        if result.returncode != 0:
            print("Build failed!", file=sys.stderr)
            return result.returncode
        
        result = subprocess.run(
            ["cmake", "--build", str(build_dir)],
            cwd=REPO_ROOT,
            capture_output=not verbose,
        )
        if result.returncode != 0:
            print("Build failed!", file=sys.stderr)
            return result.returncode
    
    print("Running tests...")
    result = subprocess.run(
        ["ctest", "--output-on-failure"] + (["--verbose"] if verbose else []),
        cwd=build_dir,
    )
    return result.returncode


def cmd_build(argv: list[str]) -> int:
    """Build framework library."""
    do_clean = "--clean" in argv
    build_apps = "--apps" in argv
    build_tests = "--tests" in argv or "--tests" not in argv
    
    build_dir = REPO_ROOT / "build"
    
    if do_clean:
        print("Cleaning build directory...")
        import shutil
        if build_dir.exists():
            shutil.rmtree(build_dir)
    
    build_dir.mkdir(exist_ok=True)
    
    cmake_args = [
        "cmake", "-S", str(REPO_ROOT), "-B", str(build_dir),
        f"-DEFW_BUILD_APPLICATIONS={'ON' if build_apps else 'OFF'}",
        f"-DEFW_BUILD_TESTS={'ON' if build_tests else 'OFF'}",
    ]
    
    print("Configuring...")
    result = subprocess.run(cmake_args, cwd=REPO_ROOT, capture_output=False)
    if result.returncode != 0:
        return result.returncode
    
    print("Building...")
    result = subprocess.run(
        ["cmake", "--build", str(build_dir)],
        cwd=REPO_ROOT,
        capture_output=False,
    )
    return result.returncode


def cmd_debug(argv: list[str]) -> int:
    """Debug and trace runtime flow."""
    # Handle --list
    if "--list" in argv:
        from codegen.debug import list_sections
        list_sections()
        return 0
    
    # Parse arguments
    graph_path = None
    sections = None
    
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--sections" and i + 1 < len(argv):
            sections = [s.strip() for s in argv[i + 1].split(",")]
            i += 2
        elif arg.startswith("--sections="):
            sections = [s.strip() for s in arg.split("=", 1)[1].split(",")]
            i += 1
        elif not arg.startswith("-"):
            graph_path = Path(arg)
            i += 1
        else:
            i += 1
    
    if not graph_path:
        print("Error: graph JSON path is required", file=sys.stderr)
        print("Usage: python3 tools/efw.py debug <graph.json> [--sections s1,s2,...]", file=sys.stderr)
        return 1
    
    if not graph_path.exists():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        return 1
    
    from codegen.debug import debug_graph
    return debug_graph(graph_path, sections)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    
    if not args:
        return cmd_studio()
    
    command = args[0]
    rest = args[1:]
    
    # Resolve aliases
    command = ALIASES.get(command, command)
    
    if command in {"help", "-h", "--help"}:
        if rest:
            print_command_help(rest[0])
        else:
            print_help()
        return 0
    
    if command not in COMMANDS:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        print(f"Available commands: {', '.join(sorted(COMMANDS.keys()))}", file=sys.stderr)
        print(f"Run 'python3 tools/efw.py help' for usage.", file=sys.stderr)
        return 2
    
    handlers = {
        "studio": lambda: cmd_studio(),
        "codegen": lambda: cmd_codegen(rest),
        "debug": lambda: cmd_debug(rest),
        "package": lambda: cmd_package(rest),
        "test": lambda: cmd_test(rest),
        "build": lambda: cmd_build(rest),
    }
    
    return handlers[command]()


if __name__ == "__main__":
    raise SystemExit(main())
