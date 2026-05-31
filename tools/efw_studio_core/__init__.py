"""Shared non-UI helpers for the EFW visual studio.

The package is intentionally free of PyQt imports so the editor widgets,
project manager, CLI checks, and future tests can reuse the same graph logic.
"""

from .templates import discover_framework_templates, node_summary, property_choices
from .pages import is_root_visible_node, node_display_name, page_for_node, page_hint, page_key, page_title, root_page, visible_nodes_for_page
from .edge_semantics import PORT_COLORS, PORT_DESCRIPTIONS, PORT_LABELS, PORT_RULES, EDGE_KIND_LABELS, apply_pair_semantics, can_connect_ports, semantic_edge_kind
from .board import apply_board_profile_defaults_to_graph

__all__ = [
    "PORT_COLORS",
    "PORT_DESCRIPTIONS",
    "PORT_LABELS",
    "PORT_RULES",
    "EDGE_KIND_LABELS",
    "apply_board_profile_defaults_to_graph",
    "apply_pair_semantics",
    "can_connect_ports",
    "semantic_edge_kind",
    "discover_framework_templates",
    "node_summary",
    "is_root_visible_node",
    "node_display_name",
    "page_for_node",
    "page_hint",
    "page_key",
    "page_title",
    "property_choices",
    "root_page",
    "visible_nodes_for_page",
]
