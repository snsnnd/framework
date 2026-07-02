"""SVD APIs."""

from __future__ import annotations

import importlib

from tools.api.capabilities import register_capability


register_capability("svd.import", "Import SVD file")
register_capability("svd.import_all", "Import SVD directory")
register_capability("svd.info", "Read SVD file info")
register_capability("svd.list", "List imported SVD MCUs")
register_capability("svd.linker", "Generate linker script")
register_capability("svd.startup", "Generate startup file")


def run_svd(argv: list[str]) -> int:
    svd_import = importlib.import_module("tools.svd.import")
    return svd_import.main(argv)
