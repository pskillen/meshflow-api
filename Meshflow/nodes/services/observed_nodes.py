"""Lookup and creation of Meshtastic ObservedNodes by node number.

A partial unique constraint (``nodes_observednode_mt_node_id_unique``) allows one Meshtastic ObservedNode per node
number. Code that finds or creates one by number goes through these helpers; the one exception is the feeder node
upsert (``packets.serializers.BaseNodeSerializer.create``), which takes the lost-race path itself. The
``dedupe_observed_nodes`` command (``nodes.services.observed_node_merge``) stays as a check, useful after a restore.

The keeper when merging is the oldest row: ``created_at`` (nulls last), then ``internal_id``.
"""

from django.db import IntegrityError, transaction
from django.db.models import F

from common.protocol import Protocol
from nodes.models import ObservedNode
from nodes.services.node_firmware import predicted_firmware_fields

# The order that picks the keeper among rows sharing a node number (also used by the merge).
KEEPER_ORDERING = (F("created_at").asc(nulls_last=True), "internal_id")


def get_meshtastic_observed_node(node_id: int) -> ObservedNode | None:
    """Return the Meshtastic ObservedNode for ``node_id``, or None."""
    return (
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id)
        .order_by(*KEEPER_ORDERING)
        .first()
    )


def get_or_create_meshtastic_observed_node(node_id: int, *, defaults: dict | None = None) -> tuple[ObservedNode, bool]:
    """Return ``(node, created)`` for a Meshtastic node number, creating the row only when none exists.

    Atomic: the lookup tolerates legacy duplicates (oldest row wins); a create that races another hits the unique
    constraint, and the loser re-reads the winner's row and returns ``(existing, False)``.
    """
    existing = get_meshtastic_observed_node(node_id)
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            return ObservedNode.objects.get_or_create(
                protocol=Protocol.MESHTASTIC,
                meshtastic_node_id=node_id,
                defaults={**predicted_firmware_fields(node_id), **(defaults or {})},
            )
    except IntegrityError:
        existing = get_meshtastic_observed_node(node_id)
        if existing is None:
            raise
        return existing, False
