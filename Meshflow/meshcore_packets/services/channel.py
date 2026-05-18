"""Resolve MeshCore MessageChannel rows per ADR-0002."""

from common.protocol import Protocol
from constellations.models import MessageChannel
from nodes.models import ManagedNode


def resolve_mc_channel(observer: ManagedNode, channel_idx: int | None) -> MessageChannel | None:
    """Map (observer constellation, mc_channel_idx) to a MessageChannel; auto-create placeholder."""
    if channel_idx is None:
        return None
    constellation = observer.constellation
    channel, created = MessageChannel.objects.get_or_create(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=channel_idx,
        defaults={"name": f"MC channel {channel_idx}"},
    )
    if created:
        pass
    return channel
