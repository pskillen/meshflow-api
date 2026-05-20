"""Resolve MeshCore MessageChannel rows per ADR-0002."""

from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel
from nodes.models import ManagedNode

MC_CHANNEL_IDX_MAX = 63


def resolve_mc_channel(observer: ManagedNode, channel_idx: int | None) -> MessageChannel | None:
    """Map (observer constellation, mc_channel_idx) to a MessageChannel; prefer feeder M2M."""
    if channel_idx is None:
        return None
    channel_idx = int(channel_idx)
    if channel_idx < 0 or channel_idx > MC_CHANNEL_IDX_MAX:
        return None

    existing = observer.mc_channels.filter(mc_channel_idx=channel_idx).first()
    if existing:
        return existing

    constellation = observer.constellation
    channel, created = MessageChannel.objects.get_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=channel_idx,
        defaults={
            "name": f"MC channel {channel_idx}",
            "mc_channel_type": MeshCoreChannelType.PUBLIC,
        },
    )
    if created:
        observer.mc_channels.add(channel)
    return channel
