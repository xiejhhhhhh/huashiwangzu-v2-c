"""Shared TypedDicts for JSON blob fields that were previously typed as Any."""

from __future__ import annotations

from typing import TypedDict

# ── App / Manifest declarations ──────────────────────────────────────

class CapabilitiesDict(TypedDict, total=False):
    """App manifest capabilities declaration."""
    _: str  # marker to prevent empty-typed-dict warnings


class PublicActionDict(TypedDict, total=False):
    """Single public action in app manifest."""
    action: str
    label: str
    icon: str


class PermissionDeclarationDict(TypedDict, total=False):
    """App manifest permission_declaration."""
    required: list[str]
    optional: list[str]


class MigrationDeclarationDict(TypedDict, total=False):
    """App manifest db_migration_declaration."""
    version: str
    scripts: list[str]


class EventHandlerDeclarationDict(TypedDict, total=False):
    """App manifest event_handler_declaration."""
    events: list[str]


class DependencyDeclarationDict(TypedDict, total=False):
    """App manifest dependency_declaration."""
    packages: list[str]


class OpenableTypesDeclarationDict(TypedDict, total=False):
    """App manifest openable_types_declaration."""
    extensions: list[str]


# ── Desktop state ───────────────────────────────────────────────────

class DesktopStateDict(TypedDict, total=False):
    """User desktop state (window positions, etc.)."""
    windows: list[dict]
    tray: dict
    icon_positions: dict


class DesktopAuditParamsDict(TypedDict, total=False):
    """Audit log params."""
    _: str


# ── Office package ──────────────────────────────────────────────────

class PackageInfoDict(TypedDict, total=False):
    """Office package summary."""
    id: int | None
    name: str


class VersionInfoDict(TypedDict, total=False):
    """Office version summary."""
    id: int | None
    version_number: int | None


# ── Gate pool ────────────────────────────────────────────────────────

class GateConfigDict(TypedDict, total=False):
    """Single gate configuration."""
    name: str
    provider: str
    model: str
    base_url: str
    api_key: str
    max_retries: int
    timeout: int


class GateBodyDict(TypedDict, total=False):
    """Gate request body."""
    model: str
    messages: list
    max_tokens: int
