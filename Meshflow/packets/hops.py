"""Hop-count rules for Meshtastic observations (2.8 dynamic hop limits).

2.8 HopScaling lowers ``hop_start`` on broadcast POSITION, TELEMETRY, NODEINFO and NEIGHBORINFO depending on mesh
density, and a 2.8 relay can send ``hop_start == 0`` on a packet that travelled. So:

* ``hop_start == 0`` with no bitfield means the hop count is unknown (not direct).
* The node's inferred max hops is set from unscaled ports (authoritative, may go down) and only raised by scaled
  ports, and only when no authoritative value is younger than :data:`AUTHORITATIVE_MAX_AGE`.
"""

from datetime import timedelta
from typing import Optional

from django.utils import timezone

SCALED_PORTS = frozenset({"POSITION_APP", "TELEMETRY_APP", "NODEINFO_APP", "NEIGHBORINFO_APP"})
AUTHORITATIVE_MAX_AGE = timedelta(days=7)


def hops_unknown(hop_start: Optional[int], hop_limit: Optional[int], bitfield: Optional[int]) -> bool:
    """True when hop_start/hop_limit cannot tell us how far the packet travelled."""
    if hop_start is None or hop_limit is None:
        return True
    return hop_start == 0 and bitfield is None


def observation_hop_count(observation) -> Optional[int]:
    """Hops the packet travelled (hop_start - hop_limit), or None when unknown or inconsistent."""
    if hops_unknown(observation.hop_start, observation.hop_limit, getattr(observation, "bitfield", None)):
        return None
    hops = observation.hop_start - observation.hop_limit
    return hops if hops >= 0 else None


def observation_is_direct(observation) -> bool:
    """True when the packet was heard directly from the sender; False when direct is not known."""
    return observation_hop_count(observation) == 0


def update_inferred_max_hops(node, observation, port_num, *, via_mqtt: bool = False) -> bool:
    """Update ``node``'s ``NodeLatestStatus.meshtastic_inferred_max_hops`` from an observation.

    Returns True when the stored value (with its ``_at`` and ``_source``) was written.
    """
    from nodes.models import NodeLatestStatus

    hop_start = getattr(observation, "hop_start", None) if observation else None
    hop_limit = getattr(observation, "hop_limit", None) if observation else None
    if via_mqtt or hop_start is None:
        return False
    if hop_limit is not None and hop_start < hop_limit:
        return False
    if hop_start == 0 and getattr(observation, "bitfield", None) is None:
        return False

    status, _ = NodeLatestStatus.objects.get_or_create(node=node)
    now = timezone.now()
    current = status.meshtastic_inferred_max_hops

    if port_num in SCALED_PORTS and current is not None:
        if hop_start <= current:
            return False
        source = status.meshtastic_inferred_max_hops_source
        at = status.meshtastic_inferred_max_hops_at
        if source and source not in SCALED_PORTS and at is not None and now - at < AUTHORITATIVE_MAX_AGE:
            return False

    status.meshtastic_inferred_max_hops = hop_start
    status.meshtastic_inferred_max_hops_at = now
    status.meshtastic_inferred_max_hops_source = port_num
    status.save(
        update_fields=[
            "meshtastic_inferred_max_hops",
            "meshtastic_inferred_max_hops_at",
            "meshtastic_inferred_max_hops_source",
        ]
    )
    return True
