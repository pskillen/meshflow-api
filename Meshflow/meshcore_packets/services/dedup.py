"""MeshCore packet deduplication (ADR-0004)."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone as django_timezone

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
    pkt_hash: int | None,
    rx_time,
    event_type: str | None = None,
    raw_payload: str | None = None,
) -> MeshCoreRawPacket | None:
    """Find duplicate within the dedup window."""
    if pkt_hash is None:
        if not event_type or raw_payload is None:
            return None
        pkt_hash = surrogate_pkt_hash(event_type=event_type, raw_payload=raw_payload)

    window = dedup_window()
    return (
        MeshCoreRawPacket.objects.filter(
            pkt_hash=pkt_hash,
            rx_time__gte=rx_time - window,
            rx_time__lte=rx_time + window,
        )
        .order_by("first_reported_time")
        .first()
    )
