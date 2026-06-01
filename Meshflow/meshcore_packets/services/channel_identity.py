"""Canonical MeshCore MessageChannel identity (logical name/hashtag, not device index)."""

from __future__ import annotations

from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel

MC_CHANNEL_IDX_MAX = 63


def normalize_mc_hashtag(value: str | None) -> str | None:
    if value is None:
        return None
    tag = str(value).strip().lstrip("#").lower()
    return tag[:64] if tag else None


def normalize_mc_public_name(value: str | None) -> str:
    name = str(value or "Public").strip()
    return name[:100] if name else "Public"


def _parse_channel_type(value: str | int | None) -> int:
    if value is None:
        return MeshCoreChannelType.PUBLIC
    if isinstance(value, int):
        if value in MeshCoreChannelType.values:
            return value
        return MeshCoreChannelType.PUBLIC
    key = str(value).strip().upper()
    if key in MeshCoreChannelType.names:
        return MeshCoreChannelType[key]
    return MeshCoreChannelType.PUBLIC


def upsert_canonical_mc_channel(constellation, entry: dict) -> MessageChannel:
    """
    Resolve or create a constellation-scoped canonical MessageChannel from a device snapshot entry.

    HASHTAG rows are keyed by normalized mc_hashtag; PUBLIC rows by normalized name.
    """
    ch_type = _parse_channel_type(entry.get("mc_channel_type"))

    if ch_type == MeshCoreChannelType.HASHTAG:
        hashtag = normalize_mc_hashtag(entry.get("mc_hashtag") or entry.get("name"))
        if not hashtag:
            raise ValueError("Hashtag channels require a non-empty hashtag.")
        display_name = str(entry.get("name") or hashtag).strip().lstrip("#")[:100] or hashtag
        channel, _created = MessageChannel.objects.update_or_create(
            constellation=constellation,
            protocol=Protocol.MESHCORE,
            mc_channel_type=MeshCoreChannelType.HASHTAG,
            mc_hashtag=hashtag,
            defaults={
                "name": display_name,
            },
        )
        return channel

    name = normalize_mc_public_name(entry.get("name"))
    channel, _created = MessageChannel.objects.update_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
        name=name,
        defaults={
            "mc_hashtag": None,
        },
    )
    return channel


def placeholder_canonical_mc_channel(constellation, channel_idx: int) -> MessageChannel:
    """Placeholder until device sync supplies real metadata."""
    return MessageChannel.objects.get_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
        name=f"MC channel {channel_idx}",
        defaults={"mc_hashtag": None},
    )[0]
