"""Ground-station protocol APIs shared by CLI and Studio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.api.capabilities import register_capability
from tools.groundstation.profile import load_protocol_profile, write_protocol_profile_template


register_capability("groundstation.profile.load", "Load an EFW ground-station protocol profile")
register_capability("groundstation.profile.init", "Create an editable protocol profile JSON")


def load_profile(path_or_project: str | Path | None = None) -> dict[str, Any]:
    return load_protocol_profile(path_or_project)


def init_profile(path: str | Path, *, force: bool = False) -> Path:
    return write_protocol_profile_template(path, force=force)
