"""Normalize MeshCore region scope names for storage and API validation."""

from __future__ import annotations

import re

REGION_SCOPE_MAX_BYTES = 29

# Lowercase alphanumeric and hyphen per MeshCore region naming rules.
_REGION_SCOPE_RE = re.compile(r"^[a-z0-9-]+$")

_NULL_SCOPE_VALUES = frozenset({"", "*", "none", "null"})


def normalize_region_scope(value: str | None) -> str | None:
    """
    Return a canonical region name for DB storage, or None for null/legacy scope.

    Strips whitespace, lowercases, rejects invalid characters. Maps *, empty, and
    "none" to None (null region — legacy flood everywhere on mesh).
    """
    if value is None:
        return None
    raw = str(value).strip().lower().lstrip("#")
    if not raw or raw in _NULL_SCOPE_VALUES:
        return None
    if len(raw.encode("utf-8")) > REGION_SCOPE_MAX_BYTES:
        raise ValueError(f"region_scope exceeds {REGION_SCOPE_MAX_BYTES} UTF-8 bytes.")
    if not _REGION_SCOPE_RE.match(raw):
        raise ValueError("region_scope must be lowercase alphanumeric with hyphens only.")
    return raw
