"""Resolve MeshCore ingest deduplication keys (ADR-0004 partial, #387)."""

from __future__ import annotations

import hashlib
from typing import Any

from constellations.models import MessageChannel
from meshcore_packets.services.dedup import digest_to_signed_bigint, normalize_stored_pkt_hash, surrogate_pkt_hash
from nodes.models import ManagedNode


def _hash_payload(payload: str) -> int:
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return digest_to_signed_bigint(digest)


def extract_sender_timestamp(validated_data: dict[str, Any]) -> int | None:
    """Read sender_timestamp from nested capture envelope when present."""
    raw = validated_data.get("raw")
    if not isinstance(raw, dict):
        return None
    envelope = raw
    nested = raw.get("raw")
    if isinstance(nested, dict):
        envelope = nested
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("sender_timestamp")
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def channel_text_dedup_key(
    *,
    constellation_id,
    message_channel_id,
    text: str,
    sender_timestamp: int | None,
) -> int:
    """Canonical key for the same on-air channel broadcast across feeders."""
    ts_part = sender_timestamp if sender_timestamp is not None else 0
    normalized_text = (text or "").strip()
    payload = f"channel_text|{constellation_id}|{message_channel_id}|{ts_part}|{normalized_text}"
    return _hash_payload(payload)


def resolve_ingest_dedup_key(
    *,
    validated_data: dict[str, Any],
    observer: ManagedNode,
    channel: MessageChannel | None,
) -> int:
    """
      Return the dedup key to store on MeshCoreRawPacket.pkt_hash and use for lookup.

      Wire pkt_hash wins when provided. channel_text uses constellation + canonical
    channel + sender_timestamp + text. Other types fall back to envelope surrogate hash.
    """
    wire_hash = validated_data.get("pkt_hash")
    if wire_hash is not None:
        return normalize_stored_pkt_hash(wire_hash)

    payload_type = validated_data.get("payload_type")
    if payload_type == "channel_text" and channel is not None:
        return channel_text_dedup_key(
            constellation_id=observer.constellation_id,
            message_channel_id=channel.id,
            text=validated_data.get("text") or "",
            sender_timestamp=extract_sender_timestamp(validated_data),
        )

    return surrogate_pkt_hash(
        event_type=str(validated_data.get("event_type", "")),
        raw_payload=str(validated_data.get("raw", "")),
    )
