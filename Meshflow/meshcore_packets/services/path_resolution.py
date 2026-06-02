"""MeshCore path segment display and resolution via meshcore_packet_path."""

from __future__ import annotations

from typing import Any, Iterable

from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from text_messages.map_helpers import observed_node_map_position

HOP_STATUS_UNKNOWN = "unknown"
HOP_STATUS_AMBIGUOUS = "ambiguous"
HOP_STATUS_RESOLVED = "resolved"


def _normalize_segment(segment: str) -> str:
    return str(segment).strip().lower().replace("0x", "")


def _hop_from_resolution(segment: str, resolution: MeshCorePathSegmentResolution | None) -> dict[str, Any]:
    normalized = _normalize_segment(segment)
    if resolution is None:
        return {
            "hash": normalized,
            "status": HOP_STATUS_UNKNOWN,
            "node_id_str": None,
            "internal_id": None,
            "long_name": None,
            "ambiguous": False,
            "position": None,
        }

    if resolution.status == SegmentStatus.RESOLVED and resolution.observed_node_id:
        node = resolution.observed_node
        return {
            "hash": normalized,
            "status": HOP_STATUS_RESOLVED,
            "node_id_str": node.node_id_str if node else None,
            "internal_id": str(node.internal_id) if node else None,
            "long_name": node.long_name if node else None,
            "ambiguous": False,
            "position": observed_node_map_position(node),
        }

    if resolution.status == SegmentStatus.AMBIGUOUS:
        return {
            "hash": normalized,
            "status": HOP_STATUS_AMBIGUOUS,
            "node_id_str": None,
            "internal_id": None,
            "long_name": None,
            "ambiguous": True,
            "position": None,
        }

    return {
        "hash": normalized,
        "status": HOP_STATUS_UNKNOWN,
        "node_id_str": None,
        "internal_id": None,
        "long_name": None,
        "ambiguous": False,
        "position": None,
    }


def format_path_hop(segment: str, *, resolution_cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized = _normalize_segment(segment)
    if resolution_cache is not None and normalized in resolution_cache:
        return resolution_cache[normalized]
    return _hop_from_resolution(segment, None)


def format_path_hops(
    segments: list[str] | None,
    *,
    resolution_cache: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    return [format_path_hop(segment, resolution_cache=resolution_cache) for segment in segments]


def bulk_format_path_hops(segments: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Dedupe segments and load MeshCorePathSegmentResolution rows when present."""
    normalized_list: list[str] = []
    for segment in segments:
        normalized = _normalize_segment(segment)
        if normalized and normalized not in normalized_list:
            normalized_list.append(normalized)

    if not normalized_list:
        return {}

    resolutions = {
        _normalize_segment(row.segment_hash): row
        for row in MeshCorePathSegmentResolution.objects.filter(
            segment_hash__in=normalized_list,
        ).select_related("observed_node", "observed_node__latest_status")
    }

    cache: dict[str, dict[str, Any]] = {}
    for normalized in normalized_list:
        cache[normalized] = _hop_from_resolution(normalized, resolutions.get(normalized))
    return cache


def path_known_for_segments(
    segments: list[str] | None,
    *,
    resolution_cache: dict[str, dict[str, Any]] | None = None,
) -> bool:
    hops = format_path_hops(segments, resolution_cache=resolution_cache)
    if not hops:
        return False
    return all(hop.get("status") == HOP_STATUS_RESOLVED and hop.get("position") is not None for hop in hops)
