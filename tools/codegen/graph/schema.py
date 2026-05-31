"""Stable Graph schema contract shared by Studio and codegen.

This module intentionally aggregates reusable Graph schema primitives and
concrete node contracts. Keep generic concepts in graph_schema_common.py and
node-specific codegen/UI contracts in graph_node_contracts.py.
"""

from __future__ import annotations

from .node_contracts import NODE_CONTRACTS, SUPPORTED_NODE_TYPES
from .common import CALLBACK_SIGNATURES, GENERATED_FILES, GENERATION_LEVEL_LABELS, SUPPORTED_FLOW_TYPES, VALID_EDGE_KINDS


def node_contract(node_type: str) -> dict:
    return NODE_CONTRACTS[node_type]


def node_generation_label(node_type: str) -> str:
    contract = node_contract(node_type)
    return GENERATION_LEVEL_LABELS.get(contract.get("generation", ""), str(contract.get("generation", "")))
