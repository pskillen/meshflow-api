"""MeshCore packet signal receivers (identity upsert + ADVERT position)."""

from django.dispatch import receiver
from django.utils import timezone

from common.meshcore_node_helpers import normalize_mc_pubkey, resolve_or_create_mc_observed_node
from meshcore_packets.models import MeshCorePayloadType
from meshcore_packets.services.advert_fields import get_advert_field
from meshcore_packets.services.position import apply_advert_position
from meshcore_packets.signals import meshcore_packet_received


@receiver(meshcore_packet_received)
def upsert_observed_node_from_meshcore_packet(sender, packet, observer, observation, **kwargs):
    """Create or update MeshCore ObservedNode per ADR-0001."""
    last_heard = packet.rx_time or timezone.now()
    raw = packet.raw_json or {}
    mc_pubkey = packet.from_pubkey
    mc_prefix = packet.from_pubkey_prefix

    if not mc_pubkey:
        adv_key = get_advert_field(raw, "adv_key")
        if adv_key:
            try:
                mc_pubkey = normalize_mc_pubkey(str(adv_key))
            except ValueError:
                mc_pubkey = None

    if not mc_pubkey and not mc_prefix:
        return

    long_name = None
    short_name = None
    adv_name = get_advert_field(raw, "adv_name")
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

    # Position enrichment only when ADVERT coords are present; advertisement without
    # adv_lat/adv_lon must not fabricate coordinates.
    if packet.payload_type == MeshCorePayloadType.ADVERT:
        adv_type = get_advert_field(raw, "adv_type")
        update_fields: list[str] = []
        if adv_type is not None:
            try:
                node.meshcore_adv_type = int(adv_type)
                update_fields.append("meshcore_adv_type")
            except TypeError, ValueError:
                pass
        if apply_advert_position(node=node, packet=packet, raw=raw):
            pass
        if long_name:
            node.long_name = long_name
            node.short_name = short_name or node.short_name
            update_fields.extend(["long_name", "short_name"])
        if update_fields:
            node.save(update_fields=update_fields)
