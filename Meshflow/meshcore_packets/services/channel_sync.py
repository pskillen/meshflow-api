"""Reconcile API MessageChannel mirror from MeshCore device snapshot."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.mc_region_scope import normalize_region_scope
from common.protocol import Protocol
from constellations.models import MessageChannel
from meshcore_packets.services.channel_identity import (
    MC_CHANNEL_IDX_MAX,
    snapshot_entry_matches_channel,
    upsert_canonical_mc_channel,
)
from nodes.models import ManagedNode, ManagedNodeMcChannelLink


def enrich_snapshot_region_scope(managed_node: ManagedNode, entry: dict) -> dict:
    """
    When the device snapshot omits region_scope, preserve scope from the feeder's
    existing slot link when name and type still match (companion protocol gap).
    """
    entry = dict(entry)
    if "region_scope" in entry:
        try:
            scope = normalize_region_scope(entry.get("region_scope"))
        except ValueError:
            scope = None
        if scope is not None:
            entry["region_scope"] = scope
            return entry

    idx = entry.get("mc_channel_idx")
    if idx is None:
        return entry

    link = managed_node.mc_channel_links.filter(mc_channel_idx=int(idx)).select_related("message_channel").first()
    if link is None:
        return entry

    channel = link.message_channel
    if not channel.region_scope:
        return entry
    if not snapshot_entry_matches_channel(entry, channel):
        return entry
    entry["region_scope"] = channel.region_scope
    return entry


def reconcile_mc_channels(
    managed_node: ManagedNode,
    channels: list[dict],
    synced_at=None,
) -> list[MessageChannel]:
    """
    Upsert canonical MC MessageChannel rows and feeder slot links from a device snapshot.

    Each channel dict: mc_channel_idx, name, mc_channel_type (PUBLIC|HASHTAG), region_scope (optional).
    """
    if managed_node.protocol != Protocol.MESHCORE:
        raise ValueError("mc-channel-sync is only valid for MeshCore managed nodes")

    synced_dt = synced_at
    if synced_at is not None and not hasattr(synced_at, "isoformat"):
        synced_dt = parse_datetime(str(synced_at)) or timezone.now()
    elif synced_at is None:
        synced_dt = timezone.now()

    constellation = managed_node.constellation
    seen_indices: set[int] = set()
    attached: list[MessageChannel] = []

    with transaction.atomic():
        for raw_entry in channels:
            entry = enrich_snapshot_region_scope(managed_node, raw_entry)
            idx = entry.get("mc_channel_idx")
            if idx is None:
                continue
            idx = int(idx)
            if idx < 0 or idx > MC_CHANNEL_IDX_MAX:
                raise ValueError(f"mc_channel_idx out of range: {idx}")

            canonical = upsert_canonical_mc_channel(constellation, entry)
            ManagedNodeMcChannelLink.objects.update_or_create(
                managed_node=managed_node,
                mc_channel_idx=idx,
                defaults={"message_channel": canonical},
            )
            seen_indices.add(idx)
            attached.append(canonical)

        if seen_indices:
            managed_node.mc_channel_links.exclude(mc_channel_idx__in=seen_indices).delete()
        else:
            managed_node.mc_channel_links.all().delete()

        managed_node.mc_channels_synced_at = synced_dt
        managed_node.save(update_fields=["mc_channels_synced_at"])

    return attached
