"""Copy path_hashes from rx_log TEXT_MSG/PATH rows onto channel_text packet observations."""

from __future__ import annotations

import logging

from meshcore_packets.models import (
    MeshCorePacketObservation,
    MeshCorePayloadType,
    MeshCoreRawPacket,
    MeshCoreTextPacket,
)
from meshcore_packets.services.channel import resolve_mc_channel
from meshcore_packets.services.dedup import decoded_twin_window

logger = logging.getLogger(__name__)

PATH_RX_TYPENAMES = frozenset({"TEXT_MSG", "PATH"})


def rx_log_payload_typename(packet: MeshCoreRawPacket) -> str:
    raw_json = packet.raw_json or {}
    envelope = raw_json
    nested = raw_json.get("raw")
    if isinstance(nested, dict):
        envelope = nested
    if not isinstance(envelope, dict):
        return ""
    payload = envelope.get("payload") or {}
    return str(payload.get("payload_typename", "")).upper()


def channel_idx_from_packet_raw_json(packet: MeshCoreRawPacket) -> int | None:
    raw_json = packet.raw_json or {}
    if raw_json.get("channel_idx") is not None:
        return int(raw_json["channel_idx"])
    envelope = raw_json.get("raw")
    if isinstance(envelope, dict):
        payload = envelope.get("payload") or {}
        if payload.get("channel_idx") is not None:
            return int(payload["channel_idx"])
    return None


def _path_fields_from_observation(observation: MeshCorePacketObservation) -> dict | None:
    if not observation.path_hashes:
        return None
    return {
        "path_hashes": observation.path_hashes,
        "path_hash_size": observation.path_hash_size,
        "path_hash_mode": observation.path_hash_mode,
    }


def _prefer_path_fields(existing: list[str] | None, incoming: list[str]) -> list[str]:
    if not existing:
        return incoming
    if len(incoming) > len(existing):
        return incoming
    return existing


def apply_path_to_text_observation(
    *,
    text_packet: MeshCoreTextPacket,
    observer,
    path_hashes: list[str],
    path_hash_size: int | None = None,
    path_hash_mode: int | None = None,
) -> bool:
    """Merge path onto the text packet observation; prefer longer hop lists."""
    if not path_hashes:
        return False
    obs, _ = MeshCorePacketObservation.objects.get_or_create(
        packet=text_packet,
        observer=observer,
    )
    merged = _prefer_path_fields(obs.path_hashes, path_hashes)
    changed = (
        obs.path_hashes != merged
        or (path_hash_size is not None and obs.path_hash_size != path_hash_size)
        or (path_hash_mode is not None and obs.path_hash_mode != path_hash_mode)
    )
    if not changed:
        return False
    obs.path_hashes = merged
    if path_hash_size is not None:
        obs.path_hash_size = path_hash_size
    if path_hash_mode is not None:
        obs.path_hash_mode = path_hash_mode
    obs.save(
        update_fields=["path_hashes", "path_hash_size", "path_hash_mode"],
    )
    return True


def _pick_channel_text_twin(*, observer, anchor_time, channel_idx: int | None):
    window = decoded_twin_window()
    candidates = MeshCoreTextPacket.objects.filter(
        observer=observer,
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        rx_time__gte=anchor_time - window,
        rx_time__lte=anchor_time + window,
    ).order_by("-rx_time")
    count = candidates.count()
    if count == 0:
        return None
    if count == 1:
        return candidates.first()
    if channel_idx is not None:
        channel = resolve_mc_channel(observer, channel_idx)
        if channel:
            narrowed = candidates.filter(channel=channel)
            if narrowed.count() == 1:
                return narrowed.first()
    logger.debug("path_twin: %s channel_text candidates in window; skip merge", count)
    return None


def sync_path_to_channel_text_twin(
    *, packet: MeshCoreRawPacket, observer, observation: MeshCorePacketObservation
) -> bool:
    """After ingesting rx_log raw TEXT_MSG/PATH, copy path onto a nearby channel_text packet."""
    if packet.payload_type != MeshCorePayloadType.RAW:
        return False
    if packet.event_type != "rx_log_data":
        return False
    if rx_log_payload_typename(packet) not in PATH_RX_TYPENAMES:
        return False
    fields = _path_fields_from_observation(observation)
    if not fields:
        return False
    twin = _pick_channel_text_twin(
        observer=observer,
        anchor_time=packet.rx_time,
        channel_idx=channel_idx_from_packet_raw_json(packet),
    )
    if not twin:
        return False
    return apply_path_to_text_observation(text_packet=twin, observer=observer, **fields)


def sync_path_from_rx_log_twin(*, packet: MeshCoreTextPacket, observer) -> bool:
    """After ingesting channel_text, copy path from a nearby rx_log TEXT_MSG/PATH observation."""
    if packet.payload_type != MeshCorePayloadType.CHANNEL_TEXT:
        return False
    window = decoded_twin_window()
    raw_packets = MeshCoreRawPacket.objects.filter(
        observer=observer,
        payload_type=MeshCorePayloadType.RAW,
        event_type="rx_log_data",
        rx_time__gte=packet.rx_time - window,
        rx_time__lte=packet.rx_time + window,
    ).order_by("-rx_time")
    for raw in raw_packets:
        if rx_log_payload_typename(raw) not in PATH_RX_TYPENAMES:
            continue
        obs = MeshCorePacketObservation.objects.filter(packet=raw, observer=observer).first()
        if not obs:
            continue
        fields = _path_fields_from_observation(obs)
        if not fields:
            continue
        return apply_path_to_text_observation(text_packet=packet, observer=observer, **fields)
    return False
