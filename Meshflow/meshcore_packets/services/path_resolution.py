"""MeshCore path segment display and resolution via meshcore_packet_path."""

from __future__ import annotations

from typing import Any, Iterable

from django.db.models import Q

from common.protocol import Protocol
from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from nodes.models import ObservedNode
from text_messages.map_helpers import observed_node_map_position

HOP_STATUS_UNKNOWN = "unknown"
HOP_STATUS_AMBIGUOUS = "ambiguous"
HOP_STATUS_RESOLVED = "resolved"

SegmentIdentity = tuple[int | None, int | None, str]


def _normalize_segment(segment: str) -> str:
    return str(segment).strip().lower().replace("0x", "")


def segment_identity_key(
    segment: str,
    hash_mode: int | None = None,
    hash_size: int | None = None,
) -> SegmentIdentity:
    return (hash_mode, hash_size, _normalize_segment(segment))


def _empty_hop(segment: str) -> dict[str, Any]:
    normalized = _normalize_segment(segment)
    return {
        "hash": normalized,
        "status": HOP_STATUS_UNKNOWN,
        "node_id_str": None,
        "internal_id": None,
        "long_name": None,
        "short_name": None,
        "ambiguous": False,
        "position": None,
        "candidates": [],
    }


def _serialize_candidate(node: ObservedNode) -> dict[str, Any]:
    return {
        "internal_id": str(node.internal_id),
        "node_id_str": node.node_id_str,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "position": observed_node_map_position(node),
    }


def _hop_from_node(segment: str, node: ObservedNode) -> dict[str, Any]:
    normalized = _normalize_segment(segment)
    return {
        "hash": normalized,
        "status": HOP_STATUS_RESOLVED,
        "node_id_str": node.node_id_str,
        "internal_id": str(node.internal_id),
        "long_name": node.long_name,
        "short_name": node.short_name,
        "ambiguous": False,
        "position": observed_node_map_position(node),
        "candidates": [],
    }


def _hop_from_resolution(segment: str, resolution: MeshCorePathSegmentResolution | None) -> dict[str, Any]:
    normalized = _normalize_segment(segment)
    if resolution is None:
        return _empty_hop(segment)

    if resolution.status == SegmentStatus.RESOLVED and resolution.observed_node_id:
        return _hop_from_node(segment, resolution.observed_node)

    if resolution.status == SegmentStatus.AMBIGUOUS:
        return {
            "hash": normalized,
            "status": HOP_STATUS_AMBIGUOUS,
            "node_id_str": None,
            "internal_id": None,
            "long_name": None,
            "short_name": None,
            "ambiguous": True,
            "position": None,
            "candidates": [],
        }

    return _empty_hop(segment)


def _suffix_match_nodes(segment: str) -> list[ObservedNode]:
    """Match ObservedNode rows whose mc_pubkey_prefix or mc_pubkey ends with segment hex."""
    normalized = _normalize_segment(segment)
    if not normalized:
        return []
    return list(
        ObservedNode.objects.filter(protocol=Protocol.MESHCORE)
        .filter(Q(mc_pubkey_prefix__iendswith=normalized) | Q(mc_pubkey__iendswith=normalized))
        .select_related("latest_status")
        .distinct()[:20]
    )


def _apply_auto_matcher(hop: dict[str, Any]) -> dict[str, Any]:
    if hop["status"] != HOP_STATUS_UNKNOWN:
        return hop
    nodes = _suffix_match_nodes(hop["hash"])
    if not nodes:
        return hop
    if len(nodes) == 1:
        return _hop_from_node(hop["hash"], nodes[0])
    return {
        "hash": hop["hash"],
        "status": HOP_STATUS_AMBIGUOUS,
        "node_id_str": None,
        "internal_id": None,
        "long_name": None,
        "short_name": None,
        "ambiguous": True,
        "position": None,
        "candidates": [_serialize_candidate(node) for node in nodes],
    }


def _coerce_segment_ref(item: str | dict[str, Any]) -> SegmentIdentity:
    if isinstance(item, str):
        return segment_identity_key(item)
    return segment_identity_key(
        item["segment"],
        item.get("hash_mode"),
        item.get("hash_size"),
    )


def _lookup_resolution_row(
    segment: str,
    hash_mode: int | None,
    hash_size: int | None,
    by_triple: dict[SegmentIdentity, MeshCorePathSegmentResolution],
    by_hash: dict[str, list[MeshCorePathSegmentResolution]],
) -> MeshCorePathSegmentResolution | None:
    key = segment_identity_key(segment, hash_mode, hash_size)
    row = by_triple.get(key)
    if row is not None:
        return row
    normalized = _normalize_segment(segment)
    rows = by_hash.get(normalized) or []
    if len(rows) == 1:
        return rows[0]
    for candidate in rows:
        if candidate.hash_mode == hash_mode and candidate.hash_size == hash_size:
            return candidate
    return None


def format_path_hop(
    segment: str,
    *,
    hash_mode: int | None = None,
    hash_size: int | None = None,
    resolution_cache: dict[SegmentIdentity, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    key = segment_identity_key(segment, hash_mode, hash_size)
    if resolution_cache is not None and key in resolution_cache:
        return resolution_cache[key]
    hop = _apply_auto_matcher(_empty_hop(segment))
    return hop


def format_path_hops(
    segments: list[str] | None,
    *,
    hash_mode: int | None = None,
    hash_size: int | None = None,
    resolution_cache: dict[SegmentIdentity, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    return [
        format_path_hop(segment, hash_mode=hash_mode, hash_size=hash_size, resolution_cache=resolution_cache)
        for segment in segments
    ]


def bulk_format_path_hops(
    segment_refs: Iterable[str | dict[str, Any]],
) -> dict[SegmentIdentity, dict[str, Any]]:
    """Load segment resolutions and auto-matcher results for message heard[] bulk cache."""
    keys: list[SegmentIdentity] = []
    seen: set[SegmentIdentity] = set()
    for item in segment_refs:
        key = _coerce_segment_ref(item)
        if key[2] and key not in seen:
            seen.add(key)
            keys.append(key)

    if not keys:
        return {}

    segment_hashes = {key[2] for key in keys}
    rows = list(
        MeshCorePathSegmentResolution.objects.filter(
            segment_hash__in=segment_hashes,
        ).select_related("observed_node", "observed_node__latest_status")
    )
    by_triple: dict[SegmentIdentity, MeshCorePathSegmentResolution] = {}
    by_hash: dict[str, list[MeshCorePathSegmentResolution]] = {}
    for row in rows:
        normalized = _normalize_segment(row.segment_hash)
        triple = segment_identity_key(normalized, row.hash_mode, row.hash_size)
        by_triple[triple] = row
        by_hash.setdefault(normalized, []).append(row)

    cache: dict[SegmentIdentity, dict[str, Any]] = {}
    for hash_mode, hash_size, normalized in keys:
        key = (hash_mode, hash_size, normalized)
        resolution = _lookup_resolution_row(normalized, hash_mode, hash_size, by_triple, by_hash)
        hop = _hop_from_resolution(normalized, resolution)
        if hop["status"] == HOP_STATUS_UNKNOWN:
            hop = _apply_auto_matcher(hop)
        elif hop["status"] == HOP_STATUS_AMBIGUOUS and not hop["candidates"]:
            nodes = _suffix_match_nodes(normalized)
            if nodes:
                hop = {**hop, "candidates": [_serialize_candidate(node) for node in nodes]}
        cache[key] = hop
    return cache


def path_known_for_segments(
    segments: list[str] | None,
    *,
    hash_mode: int | None = None,
    hash_size: int | None = None,
    resolution_cache: dict[SegmentIdentity, dict[str, Any]] | None = None,
) -> bool:
    hops = format_path_hops(
        segments,
        hash_mode=hash_mode,
        hash_size=hash_size,
        resolution_cache=resolution_cache,
    )
    if not hops:
        return False
    return all(hop.get("status") == HOP_STATUS_RESOLVED and hop.get("position") is not None for hop in hops)
