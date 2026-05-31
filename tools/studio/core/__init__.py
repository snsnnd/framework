"""Studio-only helpers for templates, pages and board resources."""

from .board import apply_board_profile_defaults_to_graph
from .pages import is_root_visible_node, node_display_name, page_for_node, page_hint, page_key, page_title, root_page, visible_nodes_for_page
from .templates import discover_framework_templates, node_summary, property_choices

__all__ = [
    "apply_board_profile_defaults_to_graph",
    "discover_framework_templates",
    "node_summary",
    "property_choices",
    "is_root_visible_node",
    "node_display_name",
    "page_for_node",
    "page_hint",
    "page_key",
    "page_title",
    "root_page",
    "visible_nodes_for_page",
]
