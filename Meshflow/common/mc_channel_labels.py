"""Display labels and apply payloads for MeshCore MessageChannel rows."""

from __future__ import annotations

from constellations.models import MeshCoreChannelType, MessageChannel
from nodes.models import ManagedNode, ManagedNodeMcChannelLink


def mc_channel_admin_label(channel: MessageChannel) -> str:
    """Human label for admin lists: #hashtag for HASHTAG, plain name for PUBLIC."""
    if channel.mc_channel_type == MeshCoreChannelType.HASHTAG:
        tag = (channel.mc_hashtag or channel.name or "").strip().lstrip("#")
        if tag:
            return f"#{tag}"
    name = (channel.name or "").strip()
    if name:
        return name
    return str(channel.pk)


def mc_channel_display_label(channel: MessageChannel) -> str:
    """Operator-facing label (Messages UI, constellation channel lists)."""
    return mc_channel_admin_label(channel)


def mc_channel_type_name(channel: MessageChannel) -> str:
    if channel.mc_channel_type is None:
        return "—"
    return MeshCoreChannelType(channel.mc_channel_type).name


def message_channel_to_apply_entry(
    channel: MessageChannel,
    *,
    managed_node: ManagedNode | None = None,
    mc_channel_idx: int | None = None,
) -> dict:
    """Build one apply_mc_channel_config entry from a canonical channel and feeder slot."""
    if mc_channel_idx is None and managed_node is not None:
        link = ManagedNodeMcChannelLink.objects.filter(
            managed_node=managed_node,
            message_channel=channel,
        ).first()
        if link is not None:
            mc_channel_idx = link.mc_channel_idx
    if mc_channel_idx is None:
        raise ValueError("mc_channel_idx is required to apply channel config to a feeder device")

    ch_type = mc_channel_type_name(channel)
    if ch_type == "—":
        ch_type = "PUBLIC"
    entry = {
        "mc_channel_idx": mc_channel_idx,
        "name": channel.name,
        "mc_channel_type": ch_type,
    }
    if channel.mc_channel_type == MeshCoreChannelType.HASHTAG:
        tag = (channel.mc_hashtag or channel.name or "").strip().lstrip("#")
        entry["mc_hashtag"] = tag[:64] if tag else None
        if tag:
            entry["name"] = tag[:100]
    return entry


def managed_node_mc_channel_links(managed_node: ManagedNode):
    """Feeder slot links with canonical channels, ordered by device index."""
    from common.protocol import Protocol

    return (
        managed_node.mc_channel_links.filter(message_channel__protocol=Protocol.MESHCORE)
        .select_related("message_channel")
        .order_by("mc_channel_idx")
    )


def managed_node_mc_channels_queryset(managed_node):
    """Canonical MC channel rows for a MeshCore feeder (legacy queryset helper)."""
    from common.protocol import Protocol

    return MessageChannel.objects.filter(
        feeder_links__managed_node=managed_node,
        protocol=Protocol.MESHCORE,
    ).order_by("feeder_links__mc_channel_idx")
