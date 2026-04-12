"""Public data types returned by the OpenDecree SDK.

All types are frozen, slotted dataclasses — immutable and fast.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfigValue:
    """A single configuration value."""

    field_path: str
    value: str
    checksum: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Change:
    """A configuration change event from a subscription."""

    field_path: str
    old_value: str | None
    new_value: str | None
    version: int
    changed_by: str = ""


@dataclass(frozen=True, slots=True)
class ServerVersion:
    """Server version information from the VersionService."""

    version: str
    commit: str
