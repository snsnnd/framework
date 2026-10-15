"""Project-extensible EFW ground-station protocol profiles."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


DEFAULT_PROTOCOL_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "protocol": {
        "name": "EFW GroundStation",
        "base": "LiteTune",
        "version": "0.5.0",
    },
    "wire": {
        "framing": "cobs-zero-delimited",
        "endianness": "little",
        "crc": "crc16-mcrf4xx",
        "max_decoded_frame": 2048,
    },
    "features": {
        "LOG_PACKED": 0,
        "PARAM_GET": 1,
        "PARAM_SET": 2,
        "CMD": 3,
        "LOG_TEXT": 4,
    },
    "frame_types": {
        "DISCOVER": 0x01,
        "REGISTER_BEGIN": 0x02,
        "REGISTER_LOG_LAYOUT": 0x03,
        "REGISTER_PARAM_DESC": 0x04,
        "REGISTER_CMD_DESC": 0x05,
        "REGISTER_END": 0x06,
        "STATUS": 0x07,
        "LOG_REPORT": 0x11,
        "LOG_TEXT": 0x12,
        "PARAM_SET": 0x21,
        "PARAM_GET": 0x22,
        "PARAM_REPORT": 0x23,
        "CMD_REQUEST": 0x31,
        "CMD_RESPONSE": 0x32,
    },
    "project_frame_range": [0x40, 0x7F],
    "project_status_range": [0x80, 0xFF],
    "value_types": {
        "bool": 0x01,
        "u8": 0x02,
        "i8": 0x03,
        "u16": 0x04,
        "i16": 0x05,
        "u32": 0x06,
        "i32": 0x07,
        "u64": 0x08,
        "i64": 0x09,
        "f32": 0x0A,
        "f64": 0x0B,
        "string": 0x0C,
        "bytes": 0x0D,
        "enum_u8": 0x0E,
    },
    "efw": {
        "debug_namespaces": ["hal", "sensor", "actuator", "algo", "sm", "module", "custom"],
        "record_events": ["SCHEMA", "LOG_REPORT", "LOG_TEXT", "PARAM_REPORT", "CMD_RESPONSE", "STATUS"],
        "builtin_commands": ["debug.list", "debug.stats", "debug.snapshot"],
    },
    "extensions": {
        "frame_types": {},
        "value_types": {},
        "commands": {},
        "params": {},
        "log_layouts": {},
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def resolve_profile_path(path_or_project: str | Path | None) -> Path | None:
    if not path_or_project:
        return None
    path = Path(path_or_project).expanduser().resolve()
    data = load_json(path)
    if "protocol" in data or "wire" in data or "extensions" in data:
        return path
    profile = data.get("protocol_profile") or data.get("groundstation_profile")
    if not profile:
        return None
    profile_path = Path(str(profile)).expanduser()
    return profile_path.resolve() if profile_path.is_absolute() else (path.parent / profile_path).resolve()


def load_protocol_profile(path_or_project: str | Path | None = None) -> dict[str, Any]:
    profile_path = resolve_profile_path(path_or_project)
    profile = copy.deepcopy(DEFAULT_PROTOCOL_PROFILE)
    if profile_path is not None:
        profile = deep_merge(profile, load_json(profile_path))
        profile["path"] = str(profile_path)
    return profile


def requested_features_mask(profile: dict[str, Any]) -> int:
    features = profile.get("features", {})
    if not isinstance(features, dict):
        return 0
    mask = 0
    for bit in features.values():
        mask |= 1 << int(bit)
    return mask


def write_protocol_profile_template(path: str | Path, *, force: bool = False) -> Path:
    output = Path(path).expanduser().resolve()
    if output.exists() and not force:
        raise FileExistsError(f"protocol profile already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(DEFAULT_PROTOCOL_PROFILE, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return output
