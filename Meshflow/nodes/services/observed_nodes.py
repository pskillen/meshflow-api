"""Lookup and creation of Meshtastic ObservedNodes by node number.

``ObservedNode`` has no unique constraint on ``meshtastic_node_id`` yet, so concurrent first-sightings can leave
duplicate rows. Every code path that finds or creates a Meshtastic ObservedNode by number goes through these helpers,
so a duplicate degrades to "use the oldest row" instead of ``MultipleObjectsReturned``. The ``dedupe_observed_nodes``
command (``nodes.services.observed_node_merge``) merges the duplicates away.

The keeper is the oldest row: ``created_at`` (nulls last), then ``internal_id``.
"""

import logging

from django.db.models import F

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.protocol import Protocol
from nodes.models import ObservedNode

logger = logging.getLogger(__name__)

# The order that picks the keeper among rows sharing a node number (also used by the merge).
KEEPER_ORDERING = (F("created_at").asc(nulls_last=True), "internal_id")


def get_meshtastic_observed_node(node_id: int) -> ObservedNode | None:
    """Return the Meshtastic ObservedNode for ``node_id``, or None.

    When duplicates exist, returns the oldest row and logs one WARNING naming the node and the row count.
    """
    rows = list(
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id).order_by(
            *KEEPER_ORDERING
        )[:2]
    )
    if not rows:
        return None
    if len(rows) > 1:
        count = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id).count()
        logger.warning(
            "Duplicate ObservedNode rows for %s: %d rows share this node number; using the oldest (%s)",
            meshtastic_id_to_hex(node_id),
            count,
            rows[0].internal_id,
        )
    return rows[0]


def get_or_create_meshtastic_observed_node(node_id: int, *, defaults: dict | None = None) -> tuple[ObservedNode, bool]:
    """Return ``(node, created)`` for a Meshtastic node number, creating the row only when none exists.

    Not atomic: a concurrent create can still produce a duplicate until the unique constraint lands.
    """
    node = get_meshtastic_observed_node(node_id)
    if node is not None:
        return node, False
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC,
        meshtastic_node_id=node_id,
        **(defaults or {}),
    )
    return node, True
