"""MeshCore path segment display (v1: no hash→ObservedNode linking)."""

from __future__ import annotations

from typing import Any, Iterable

HOP_STATUS_UNKNOWN = "unknown"
HOP_STATUS_AMBIGUOUS = "ambiguous"
HOP_STATUS_RESOLVED = "resolved"


def _normalize_segment(segment: str) -> str:
    return str(segment).strip().lower().replace("0x", "")


def format_path_hop(segment: str) -> dict[str, Any]:
    """One display hop for a wire path segment (v1: always unknown)."""
    normalized = _normalize_segment(segment)
    return {
        "hash": normalized,
        "status": HOP_STATUS_UNKNOWN,
        "node_id_str": None,
        "internal_id": None,
        "long_name": None,
        "ambiguous": False,
    }


def format_path_hops(segments: list[str] | None) -> list[dict[str, Any]]:
    if not segments:
        return []
    return [format_path_hop(segment) for segment in segments]


def bulk_format_path_hops(segments: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Dedupe segments for a single message list response."""
    cache: dict[str, dict[str, Any]] = {}
    for segment in segments:
        normalized = _normalize_segment(segment)
        if normalized and normalized not in cache:
            cache[normalized] = format_path_hop(normalized)
    return cache


def path_known_for_segments(segments: list[str] | None) -> bool:
    """True only when all hops are resolved (v1 always false)."""
    hops = format_path_hops(segments)
    return bool(hops) and all(hop.get("status") == HOP_STATUS_RESOLVED for hop in hops)
