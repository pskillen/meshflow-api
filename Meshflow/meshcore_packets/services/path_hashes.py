"""Split MeshCore wire ``path`` hex into hop hash segments (server-side)."""

from __future__ import annotations

from typing import Any


def split_path_hex(path: str, path_hash_size: int) -> list[str]:
    """Split concatenated path hex into per-hop segments (``path_hash_size`` bytes each)."""
    if not path or not isinstance(path, str):
        return []
    size = int(path_hash_size or 2)
    if size < 1:
        size = 2
    width = size * 2
    return [path[i : i + width] for i in range(0, len(path), width) if path[i : i + width]]


def _path_from_payload(payload: dict) -> tuple[list[str] | None, int | None, int | None]:
    if not isinstance(payload, dict):
        return None, None, None
    existing = payload.get("path_hashes")
    if isinstance(existing, list) and existing:
        return [str(p) for p in existing], payload.get("path_hash_size"), payload.get("path_hash_mode")
    path = payload.get("path")
    size = payload.get("path_hash_size")
    if size is None:
        size = 2
    if isinstance(path, list) and path:
        return [str(p) for p in path], int(size), payload.get("path_hash_mode")
    if isinstance(path, str) and path:
        segments = split_path_hex(path, int(size))
        return segments or None, int(size), payload.get("path_hash_mode")
    return None, payload.get("path_hash_size"), payload.get("path_hash_mode")


def path_hashes_from_ingest(validated_data: dict[str, Any]) -> list[str] | None:
    """Resolve path_hashes from ingest body or nested capture envelope."""
    segments, _, _ = _path_from_payload(validated_data)
    if segments:
        return segments

    raw = validated_data.get("raw")
    if not isinstance(raw, dict):
        return None

    envelope = raw
    if isinstance(raw.get("raw"), dict):
        envelope = raw["raw"]
    elif raw.get("protocol") != "meshcore" and isinstance(raw.get("payload"), dict):
        envelope = raw

    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    segments, _, _ = _path_from_payload(payload or {})
    return segments


def enrich_validated_data_paths(validated_data: dict[str, Any]) -> None:
    """Populate ``path_hashes`` on validated_data when only wire ``path`` is present."""
    segments = path_hashes_from_ingest(validated_data)
    if segments and not validated_data.get("path_hashes"):
        validated_data["path_hashes"] = segments
