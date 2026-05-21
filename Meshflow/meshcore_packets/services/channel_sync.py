"""Reconcile API MessageChannel mirror from MeshCore device snapshot."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel
from nodes.models import ManagedNode

MC_CHANNEL_IDX_MAX = 63


def _parse_channel_type(value: str | int | None) -> int | None:
    if value is None:
        return MeshCoreChannelType.PUBLIC
    if isinstance(value, int):
        if value in MeshCoreChannelType.values:
            return value
        return None
    key = str(value).strip().upper()
    if key in MeshCoreChannelType.names:
        return MeshCoreChannelType[key]
    return None


def reconcile_mc_channels(
    managed_node: ManagedNode,
    channels: list[dict],
    synced_at=None,
) -> list[MessageChannel]:
    """
    Upsert constellation MC MessageChannel rows and set managed_node.mc_channels to match snapshot.

    Each channel dict: mc_channel_idx, name, mc_channel_type (PUBLIC|HASHTAG), mc_hashtag (optional).
    """
    if managed_node.protocol != Protocol.MESHCORE:
        raise ValueError("mc-channel-sync is only valid for MeshCore managed nodes")

    constellation = managed_node.constellation
    synced_dt = synced_at
    if synced_at is not None and not hasattr(synced_at, "isoformat"):
        synced_dt = parse_datetime(str(synced_at)) or timezone.now()
    elif synced_at is None:
        synced_dt = timezone.now()

    attached: list[MessageChannel] = []

    with transaction.atomic():
        for entry in channels:
            idx = entry.get("mc_channel_idx")
            if idx is None:
                continue
            idx = int(idx)
            if idx < 0 or idx > MC_CHANNEL_IDX_MAX:
                raise ValueError(f"mc_channel_idx out of range: {idx}")

            name = str(entry.get("name") or f"MC channel {idx}")[:100]
            ch_type = _parse_channel_type(entry.get("mc_channel_type"))
            if ch_type is None:
                raise ValueError(f"invalid mc_channel_type: {entry.get('mc_channel_type')}")

            hashtag = entry.get("mc_hashtag")
            if hashtag is not None:
                hashtag = str(hashtag).strip().lstrip("#")[:64] or None

            if ch_type == MeshCoreChannelType.HASHTAG and not hashtag:
                name_for_hash = name if name.startswith("#") else f"#{name}"
                hashtag = name_for_hash.lstrip("#")[:64]

            channel, _created = MessageChannel.objects.update_or_create(
                constellation=constellation,
                protocol=Protocol.MESHCORE,
                mc_channel_idx=idx,
                defaults={
                    "name": name,
                    "mc_channel_type": ch_type,
                    "mc_hashtag": hashtag if ch_type == MeshCoreChannelType.HASHTAG else None,
                },
            )
            attached.append(channel)

        managed_node.mc_channels.set(attached)
        managed_node.mc_channels_synced_at = synced_dt
        managed_node.save(update_fields=["mc_channels_synced_at"])

    return attached
