"""Display labels and apply payloads for MeshCore MessageChannel rows."""

from __future__ import annotations

from constellations.models import MeshCoreChannelType, MessageChannel


def mc_channel_admin_label(channel: MessageChannel) -> str:
    """Human label for admin lists: #hashtag for HASHTAG, plain name for PUBLIC."""
    if channel.mc_channel_type == MeshCoreChannelType.HASHTAG:
        tag = (channel.mc_hashtag or channel.name or "").strip().lstrip("#")
        if tag:
            return f"#{tag}"
    name = (channel.name or "").strip()
    if name:
        return name
    if channel.mc_channel_idx is not None:
        return f"slot {channel.mc_channel_idx}"
    return str(channel.pk)


def mc_channel_type_name(channel: MessageChannel) -> str:
    if channel.mc_channel_type is None:
        return "—"
    return MeshCoreChannelType(channel.mc_channel_type).name


def message_channel_to_apply_entry(channel: MessageChannel) -> dict:
    """Build one apply_mc_channel_config entry from a MessageChannel row."""
    ch_type = mc_channel_type_name(channel)
    if ch_type == "—":
        ch_type = "PUBLIC"
    entry = {
        "mc_channel_idx": channel.mc_channel_idx,
        "name": channel.name,
        "mc_channel_type": ch_type,
    }
    if channel.mc_channel_type == MeshCoreChannelType.HASHTAG:
        tag = (channel.mc_hashtag or channel.name or "").strip().lstrip("#")
        entry["mc_hashtag"] = tag[:64] if tag else None
        if tag:
            entry["name"] = tag[:100]
    return entry


def managed_node_mc_channels_queryset(managed_node):
    """MC channel rows linked on a MeshCore feeder (device mirror)."""
    from common.protocol import Protocol

    return managed_node.mc_channels.filter(protocol=Protocol.MESHCORE).order_by("mc_channel_idx")
