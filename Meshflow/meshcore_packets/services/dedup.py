"""MeshCore packet deduplication (ADR-0004)."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings

from meshcore_packets.models import MeshCoreRawPacket


def dedup_window() -> timedelta:
    minutes = getattr(settings, "MESHCORE_PACKET_DEDUP_WINDOW_MINUTES", 10)
    return timedelta(minutes=minutes)


def decoded_twin_window() -> timedelta:
    seconds = getattr(settings, "MESHCORE_DECODED_TWIN_WINDOW_SECONDS", 30)
    return timedelta(seconds=seconds)


def surrogate_pkt_hash(*, event_type: str, raw_payload: str) -> int:
    digest = hashlib.sha256(f"{event_type}|{raw_payload}".encode()).hexdigest()
    return int(digest[:16], 16)


def find_existing_packet(
    *,
    dedup_key: int | None = None,
    pkt_hash: int | None = None,
    rx_time=None,
    event_type: str | None = None,
    raw_payload: str | None = None,
) -> MeshCoreRawPacket | None:
    """
    Find duplicate within the dedup window.

    Callers should pass ``dedup_key`` from ``resolve_ingest_dedup_key`` (stored on
    ``MeshCoreRawPacket.pkt_hash``). Legacy ``pkt_hash`` / surrogate args remain for
    tests that have not migrated yet.
    """
    key = dedup_key if dedup_key is not None else pkt_hash
    if key is None:
        if not event_type or raw_payload is None:
            return None
        key = surrogate_pkt_hash(event_type=event_type, raw_payload=raw_payload)

    window = dedup_window()
    return (
        MeshCoreRawPacket.objects.filter(
            pkt_hash=key,
            rx_time__gte=rx_time - window,
            rx_time__lte=rx_time + window,
        )
        .order_by("first_reported_time")
        .first()
    )
