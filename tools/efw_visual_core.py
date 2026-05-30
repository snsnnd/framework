#!/usr/bin/env python3
"""Compatibility wrapper for non-UI EFW visual helpers.

New code should import from ``efw_studio_core``.  This module remains so older
scripts that imported ``efw_visual_core`` keep working.
"""

from efw_studio_core import (  # noqa: F401
    PORT_COLORS,
    PORT_RULES,
    apply_board_profile_defaults_to_graph,
    apply_pair_semantics,
    can_connect_ports,
    discover_framework_templates,
    node_summary,
    is_root_visible_node,
    node_display_name,
    page_for_node,
    page_hint,
    page_key,
    page_title,
    property_choices,
    root_page,
    visible_nodes_for_page,
)
