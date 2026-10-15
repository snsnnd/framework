"""Board/Profile APIs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tools.api.capabilities import register_capability

try:
    from studio.model import load_board_profiles
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.studio.model import load_board_profiles  # type: ignore[no-redef]


register_capability("board.list", "List Board Profiles")
register_capability("board.info", "Read a Board Profile")
register_capability("board.import", "Import a Board Profile JSON")
register_capability("board.set_project", "Set project Board Profile")


def list_profiles() -> dict[str, dict[str, Any]]:
    return load_board_profiles()


def get_profile(profile: str) -> dict[str, Any]:
    profiles = list_profiles()
    matches = {name.casefold(): name for name in profiles}
    canonical = matches.get(profile.strip().casefold())
    if canonical is None:
        raise ValueError(f"找不到 profile: {profile}")
    return profiles[canonical]


def import_profile(file: str | Path, *, name: str | None = None, output_dir: str | Path = "data/board_profiles") -> Path:
    path = Path(file).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    if name:
        profile_name = name
    elif isinstance(data, dict) and len(data) == 1 and all(isinstance(v, dict) for v in data.values()):
        profile_name = next(iter(data))
        data = data[profile_name]
    else:
        profile_name = path.stem
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{profile_name}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def set_project_profile(project_ref: str | Path, profile: str) -> Path:
    from tools.target import GENERIC_BOARD_PROFILES, load_targets
    concrete = {name.casefold(): name for target in load_targets().values() for name in target.board_profiles}
    key = profile.strip().casefold()
    if key in GENERIC_BOARD_PROFILES:
        canonical = key
    elif key in concrete:
        canonical = concrete[key]
    else:
        raise ValueError(f"找不到可构建 profile: {profile}")
    from tools.api.project import set_project_fields
    return set_project_fields(project_ref, board=canonical)
