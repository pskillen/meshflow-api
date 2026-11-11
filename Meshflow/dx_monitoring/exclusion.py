"""DX exclusion read through identity links: an exclusion on an earlier number of a node applies to its new number.

Nothing is copied to the new row; the chain is read each time (live links only, bounded by the chain walk's limit).
"""

from __future__ import annotations

from collections.abc import Iterable

from common.protocol import Protocol
from dx_monitoring.models import DxNodeMetadata
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services.identity_chain import predecessors


def predecessor_excluded(node: ObservedNode) -> bool:
    """True when an earlier number of ``node`` is excluded from DX detection (own exclusion not checked)."""
    return DxNodeMetadata.objects.filter(observed_node__in=predecessors(node), exclude_from_detection=True).exists()


def excluded_mesh_node_ids(node_ids: Iterable[int]) -> set[int]:
    """The mesh node numbers among ``node_ids`` that are excluded, directly or through an earlier number.

    Batched for a traceroute: one query for direct exclusions, one for the links of the rest, and a chain walk only for
    the numbers that actually are a successor.
    """
    ids = {int(i) for i in node_ids}
    excluded = {
        int(i)
        for i in DxNodeMetadata.objects.filter(
            observed_node__meshtastic_node_id__in=ids,
            observed_node__protocol=Protocol.MESHTASTIC,
            exclude_from_detection=True,
        ).values_list("observed_node__meshtastic_node_id", flat=True)
    }
    rest = ids - excluded
    if not rest:
        return excluded
    linked = ObservedNodeIdentityLink.objects.filter(
        new_node__meshtastic_node_id__in=rest,
        new_node__protocol=Protocol.MESHTASTIC,
        state__in=ObservedNodeIdentityLink.LIVE_STATES,
    ).values("new_node_id")
    for node in ObservedNode.objects.filter(pk__in=linked):
        if predecessor_excluded(node):
            excluded.add(int(node.meshtastic_node_id))
    return excluded
