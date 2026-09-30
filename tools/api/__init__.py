"""Stable Python API surface for EFW tool frontends.

CLI and Studio should call modules under tools.api instead of reaching into
lower-level implementation packages directly.
"""

from .capabilities import ApiRole, Capability, get_capability, register_capability, visible_capabilities

__all__ = ["ApiRole", "Capability", "get_capability", "register_capability", "visible_capabilities"]
