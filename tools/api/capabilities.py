"""Capability registry for EFW tool frontends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApiRole(str, Enum):
    CLI = "cli"
    STUDIO = "studio"
    INTERNAL = "internal"


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    cli_visible: bool = True
    studio_visible: bool = True
    internal_only: bool = False

    def visible_to(self, role: ApiRole | str) -> bool:
        role = ApiRole(role)
        if self.internal_only:
            return role == ApiRole.INTERNAL
        if role == ApiRole.CLI:
            return self.cli_visible
        if role == ApiRole.STUDIO:
            return self.studio_visible
        return True


CAPABILITIES: dict[str, Capability] = {}


def register_capability(name: str, summary: str, *, cli_visible: bool = True, studio_visible: bool = True, internal_only: bool = False) -> Capability:
    capability = Capability(name, summary, cli_visible, studio_visible, internal_only)
    CAPABILITIES[name] = capability
    return capability


def visible_capabilities(role: ApiRole | str) -> list[Capability]:
    return sorted((cap for cap in CAPABILITIES.values() if cap.visible_to(role)), key=lambda cap: cap.name)


def get_capability(name: str) -> Capability | None:
    return CAPABILITIES.get(name)
