"""Shared non-UI helpers for the EFW visual studio.

The package is intentionally free of PyQt imports so the editor widgets,
project manager, CLI checks, and future tests can reuse the same graph logic.
"""

from .templates import discover_framework_templates, node_summary, property_choices
from .edge_semantics import PORT_COLORS, PORT_RULES, apply_pair_semantics, can_connect_ports
from .board import apply_board_profile_defaults_to_graph

__all__ = [
    "PORT_COLORS",
    "PORT_RULES",
    "apply_board_profile_defaults_to_graph",
    "apply_pair_semantics",
    "can_connect_ports",
    "discover_framework_templates",
    "node_summary",
    "property_choices",
]
