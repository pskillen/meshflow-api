"""Resolve MeshCore MessageChannel rows per ADR-0002 (canonical + per-feeder link)."""

from constellations.models import MessageChannel
from meshcore_packets.services.channel_identity import (
    MC_CHANNEL_IDX_MAX,
    placeholder_canonical_mc_channel,
)
from nodes.models import ManagedNode, ManagedNodeMcChannelLink


def resolve_mc_channel(observer: ManagedNode, channel_idx: int | None) -> MessageChannel | None:
    """Map (observer, wire channel_idx) to a canonical MessageChannel via feeder slot link."""
    if channel_idx is None:
        return None
    channel_idx = int(channel_idx)
    if channel_idx < 0 or channel_idx > MC_CHANNEL_IDX_MAX:
        return None

    link = (
        ManagedNodeMcChannelLink.objects.filter(
            managed_node=observer,
            mc_channel_idx=channel_idx,
        )
        .select_related("message_channel")
        .first()
    )
    if link:
        return link.message_channel

    constellation = observer.constellation
    canonical = placeholder_canonical_mc_channel(constellation, channel_idx)
    ManagedNodeMcChannelLink.objects.get_or_create(
        managed_node=observer,
        mc_channel_idx=channel_idx,
        defaults={"message_channel": canonical},
    )
    return canonical
