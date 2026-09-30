"""Shared utility functions for codegen and validation.

All C code generation helpers live here to avoid duplication across
generator.py, validate.py, and edge_semantics.py.
"""

from __future__ import annotations

import json
import re
from typing import Any


def c_ident(value: str, fallback: str = "app") -> str:
    """Convert a string to a valid C identifier."""
    ident = re.sub(r"[^0-9A-Za-z_]", "_", value or fallback)
    ident = re.sub(r"_+", "_", ident).strip("_") or fallback
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def macro_ident(value: str) -> str:
    """Convert a string to a C macro name (uppercase)."""
    return c_ident(value).upper()


def c_str(value: str | None) -> str:
    """Convert a Python string to a C string literal."""
    if value is None or value == "":
        return "0"
    return json.dumps(str(value))


def c_float(value) -> str:
    """Convert a Python number to a C float literal."""
    number = float(value)
    text = f"{number:.9g}"
    if "e" not in text and "." not in text:
        text += ".0"
    return f"{text}f"


def c_bool(value) -> str:
    """Convert a Python bool to a C boolean literal."""
    return "1" if bool(value) else "0"


def require(condition: bool, message: str) -> None:
    """Raise ValueError if condition is False."""
    if not condition:
        raise ValueError(message)


class ValidationError(Exception):
    """Structured validation error with severity level."""
    def __init__(self, message: str, severity: str = "error", node_id: str | None = None):
        super().__init__(message)
        self.severity = severity  # "error" or "warning"
        self.node_id = node_id


def require_v(condition: bool, message: str, severity: str = "error", node_id: str | None = None) -> None:
    """Raise ValidationError if condition is False."""
    if not condition:
        raise ValidationError(message, severity=severity, node_id=node_id)


def nodes_of(ctx: dict, type_name: str) -> list[dict]:
    """Return all nodes in ctx['nodes'] matching the given type."""
    return [node for node in ctx["nodes"] if node.get("type") == type_name]


def number_or_default(value, default):
    """Return value if it's a valid number, otherwise default."""
    return default if value in (None, "") else value


# Shared contract metadata used by validation, edge semantics, and codegen.
# Single source of truth for size/align/type of built-in EFW structs.
BUILTIN_CONTRACTS: dict[str, dict[str, Any]] = {
    "efw_pid_input_t": {"type": "efw_pid_input_t", "c_type": "efw_pid_input_t", "size": 16, "align": 4},
    "efw_pid_output_t": {"type": "efw_pid_output_t", "c_type": "efw_pid_output_t", "size": 12, "align": 4},
    "efw_motor_cmd_t": {"type": "efw_motor_cmd_t", "c_type": "efw_motor_cmd_t", "size": 8, "align": 4},
    "efw_line_tracking_data_t": {"type": "efw_line_tracking_data_t", "c_type": "efw_line_tracking_data_t", "size": 18, "align": 2},
    "float": {"type": "float", "c_type": "float", "size": 4, "align": 4},
    "uint8_t": {"type": "uint8_t", "c_type": "uint8_t", "size": 1, "align": 1},
    "uint16_t": {"type": "uint16_t", "c_type": "uint16_t", "size": 2, "align": 2},
    "uint32_t": {"type": "uint32_t", "c_type": "uint32_t", "size": 4, "align": 4},
}
