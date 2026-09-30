"""EFW project management package.

Keep package import lightweight. CLI and codegen-heavy operations are imported
on demand so Python API consumers such as Studio can import core helpers without
pulling command-line dependencies.
"""


def main(argv: list[str] | None = None) -> int:
    from .cli import main as cli_main
    return cli_main(argv)

__all__ = [
    "main",
]
