"""MeshCore packet signal receivers (Phase 1: ObservedNode upsert only)."""

from django.dispatch import receiver
from django.utils import timezone

from common.meshcore_node_helpers import resolve_or_create_mc_observed_node
from meshcore_packets.models import MeshCorePayloadType
from meshcore_packets.signals import meshcore_packet_received
from nodes.models import NodeLatestStatus


@receiver(meshcore_packet_received)
def upsert_observed_node_from_meshcore_packet(sender, packet, observer, observation, **kwargs):
    """Create or update MeshCore ObservedNode per ADR-0001."""
    last_heard = packet.rx_time or timezone.now()
    mc_pubkey = packet.from_pubkey
    mc_prefix = packet.from_pubkey_prefix

    if not mc_pubkey and not mc_prefix:
        return

    long_name = None
    short_name = None
    adv_name = (packet.raw_json or {}).get("adv_name")
    if adv_name:
        long_name = str(adv_name)[:50]
        short_name = str(adv_name)[:5]

    node = resolve_or_create_mc_observed_node(
        mc_pubkey=mc_pubkey,
        mc_pubkey_prefix=mc_prefix if not mc_pubkey else None,
        last_heard=last_heard,
        long_name=long_name,
        short_name=short_name,
    )

    if packet.payload_type == MeshCorePayloadType.ADVERT:
        raw = packet.raw_json or {}
        adv_lat = raw.get("adv_lat")
        adv_lon = raw.get("adv_lon")
        if adv_lat and adv_lon and float(adv_lat) != 0.0 and float(adv_lon) != 0.0:
            status, _ = NodeLatestStatus.objects.get_or_create(node=node)
            status.latitude = float(adv_lat)
            status.longitude = float(adv_lon)
            status.position_reported_time = last_heard
            status.save(update_fields=["latitude", "longitude", "position_reported_time"])
            if long_name:
                node.long_name = long_name
                node.short_name = short_name or node.short_name
                node.save(update_fields=["long_name", "short_name"])
