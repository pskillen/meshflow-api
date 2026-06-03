"""Canonical MeshCore MessageChannel identity (logical name/type/scope, not device index)."""

from __future__ import annotations

from common.mc_region_scope import normalize_region_scope
from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel

MC_CHANNEL_IDX_MAX = 63


def normalize_mc_hashtag_name(value: str | None) -> str | None:
    """Normalize a HASHTAG channel tag (stored in MessageChannel.name, no leading #)."""
    if value is None:
        return None
    tag = str(value).strip().lstrip("#").lower()
    return tag[:100] if tag else None


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


def _parse_region_scope(entry: dict) -> str | None:
    if "region_scope" not in entry:
        return None
    try:
        return normalize_region_scope(entry.get("region_scope"))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def snapshot_entry_matches_channel(entry: dict, channel: MessageChannel) -> bool:
    """True when a device snapshot row describes the same logical channel row."""
    ch_type = _parse_channel_type(entry.get("mc_channel_type"))
    if channel.mc_channel_type != ch_type:
        return False
    if ch_type == MeshCoreChannelType.HASHTAG:
        tag = normalize_mc_hashtag_name(entry.get("name") or entry.get("mc_hashtag"))
        return bool(tag) and tag == (channel.name or "").strip().lower()
    name = normalize_mc_public_name(entry.get("name"))
    return name == (channel.name or "").strip()


def upsert_canonical_mc_channel(constellation, entry: dict) -> MessageChannel:
    """
      Resolve or create a constellation-scoped canonical MessageChannel from a device snapshot entry.

      MC rows are keyed by (name, mc_channel_type, region_scope). For HASHTAG, name is the tag
    without #; for PUBLIC, name is the public channel name.
    """
    ch_type = _parse_channel_type(entry.get("mc_channel_type"))
    region_scope = _parse_region_scope(entry)

    if ch_type == MeshCoreChannelType.HASHTAG:
        tag = normalize_mc_hashtag_name(entry.get("name") or entry.get("mc_hashtag"))
        if not tag:
            raise ValueError("Hashtag channels require a non-empty hashtag.")
        channel, _created = MessageChannel.objects.update_or_create(
            constellation=constellation,
            protocol=Protocol.MESHCORE,
            mc_channel_type=MeshCoreChannelType.HASHTAG,
            name=tag,
            region_scope=region_scope,
            defaults={},
        )
        return channel

    name = normalize_mc_public_name(entry.get("name"))
    channel, _created = MessageChannel.objects.update_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
        name=name,
        region_scope=region_scope,
        defaults={},
    )
    return channel


def placeholder_canonical_mc_channel(constellation, channel_idx: int) -> MessageChannel:
    """Placeholder until device sync supplies real metadata."""
    return MessageChannel.objects.get_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
        name=f"MC channel {channel_idx}",
        region_scope=None,
        defaults={},
    )[0]
