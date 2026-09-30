"""Shared Graph schema and edge semantics for EFW codegen and Studio."""

from .common import CALLBACK_RETURNS, CALLBACK_SIGNATURES, GENERATED_FILES, GENERATION_LEVEL_LABELS, SUPPORTED_FLOW_TYPES, VALID_EDGE_KINDS, MULTI_INPUT_NODE_PORTS, MAPPING_ENABLED_NODE_TYPES, TRIGGER_POLICY_CHOICES, OUTPUT_MODE_CHOICES, PROCESS_MODE_CHOICES, FIELD_MAPPING_SOURCE_CHOICES, FIELD_MAPPING_TRANSFORM_CHOICES, BUILTIN_STRUCT_FIELD_TYPES, callback_signature
from .edge_semantics import PORT_COLORS, PORT_DESCRIPTIONS, PORT_LABELS, PORT_RULES, EDGE_KIND_LABELS, apply_pair_semantics, can_connect_ports, pair_has_semantics, semantic_edge_kind, edge_effect_description
from .schema import NODE_CONTRACTS, SUPPORTED_NODE_TYPES, node_contract, node_generation_label

__all__ = [
    "CALLBACK_SIGNATURES",
    "CALLBACK_RETURNS",
    "callback_signature",
    "GENERATED_FILES",
    "GENERATION_LEVEL_LABELS",
    "SUPPORTED_FLOW_TYPES",
    "VALID_EDGE_KINDS",
    "MULTI_INPUT_NODE_PORTS",
    "MAPPING_ENABLED_NODE_TYPES",
    "TRIGGER_POLICY_CHOICES",
    "OUTPUT_MODE_CHOICES",
    "PROCESS_MODE_CHOICES",
    "FIELD_MAPPING_SOURCE_CHOICES",
    "FIELD_MAPPING_TRANSFORM_CHOICES",
    "BUILTIN_STRUCT_FIELD_TYPES",
    "PORT_COLORS",
    "PORT_DESCRIPTIONS",
    "PORT_LABELS",
    "PORT_RULES",
    "EDGE_KIND_LABELS",
    "apply_pair_semantics",
    "can_connect_ports",
    "pair_has_semantics",
    "semantic_edge_kind",
    "edge_effect_description",
    "NODE_CONTRACTS",
    "SUPPORTED_NODE_TYPES",
    "node_contract",
    "node_generation_label",
]
