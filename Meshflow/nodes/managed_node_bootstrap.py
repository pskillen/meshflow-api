"""Bootstrap ObservedNode rows when creating ManagedNodes outside normal mesh flow."""

from __future__ import annotations

from django.db import transaction

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshcore_node_helpers import resolve_or_create_mc_observed_node
from common.protocol import Protocol

from .models import ManagedNode, ObservedNode


def _names_from_managed_node(managed_node: ManagedNode) -> tuple[str, str]:
    name = (managed_node.name or "").strip()
    if managed_node.protocol == Protocol.MESHTASTIC:
        display_id = meshtastic_id_to_hex(managed_node.meshtastic_node_id)
    else:
        display_id = managed_node.node_id_str
    long_name = (name or f"Unknown Node {display_id}")[:50]
    if len(name) >= 4:
        short_name = name[:5]
    elif display_id and len(display_id) >= 4:
        short_name = display_id[-4:]
    else:
        short_name = "????"
    return long_name, short_name[:5]


def find_matching_observed_node(managed_node: ManagedNode) -> ObservedNode | None:
    if managed_node.protocol == Protocol.MESHTASTIC:
        if managed_node.meshtastic_node_id is None:
            raise ValueError("Meshtastic managed node requires meshtastic_node_id")
        return ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC,
            meshtastic_node_id=managed_node.meshtastic_node_id,
        ).first()
    if managed_node.protocol == Protocol.MESHCORE:
        if not managed_node.mc_pubkey:
            raise ValueError("MeshCore managed node requires mc_pubkey")
        return ObservedNode.objects.filter(
            protocol=Protocol.MESHCORE,
            mc_pubkey=managed_node.mc_pubkey,
        ).first()
    raise ValueError(f"Unsupported protocol: {managed_node.protocol}")


@transaction.atomic
def ensure_observed_node_for_managed_node(managed_node: ManagedNode) -> tuple[ObservedNode, bool]:
    """
    Ensure a matching ObservedNode exists for a ManagedNode.

    Returns (observed_node, created) where created is True only when a new row was inserted.
    When the observed node is unclaimed, sets claimed_by to the managed node owner.
    """
    long_name, short_name = _names_from_managed_node(managed_node)
    observed = find_matching_observed_node(managed_node)
    created = False

    if observed is None:
        if managed_node.protocol == Protocol.MESHCORE:
            observed = resolve_or_create_mc_observed_node(
                mc_pubkey=managed_node.mc_pubkey,
                long_name=long_name,
                short_name=short_name,
            )
        else:
            observed = ObservedNode.objects.create(
                protocol=Protocol.MESHTASTIC,
                meshtastic_node_id=managed_node.meshtastic_node_id,
                long_name=long_name,
                short_name=short_name,
            )
        created = True

    if observed.claimed_by_id is None:
        observed.claimed_by = managed_node.owner
        observed.save(update_fields=["claimed_by"])

    return observed, created
