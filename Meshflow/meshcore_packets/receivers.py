"""MeshCore packet signal receivers (identity upsert + ADVERT position)."""

from django.dispatch import receiver
from django.utils import timezone

from common.meshcore_node_helpers import resolve_or_create_mc_observed_node
from meshcore_packets.models import MeshCorePayloadType
from meshcore_packets.services.position import apply_advert_position
from meshcore_packets.signals import meshcore_packet_received


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
        if apply_advert_position(node=node, packet=packet, raw=raw) and long_name:
            node.long_name = long_name
            node.short_name = short_name or node.short_name
            node.save(update_fields=["long_name", "short_name"])
