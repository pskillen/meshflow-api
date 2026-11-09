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

# Transports that are not the feeder's radio. A null transport counts as RF: history, and the feeder's own packets
# (absent transportMechanism is TRANSPORT_INTERNAL).
NON_RF_TRANSPORTS = frozenset({"TRANSPORT_MQTT", "TRANSPORT_MULTICAST_UDP", "TRANSPORT_UNICAST_UDP", "TRANSPORT_API"})


def observation_is_rf(observation) -> bool:
    """False when the packet reached the feeder over MQTT, UDP or the API rather than its radio."""
    if getattr(observation, "via_mqtt", None):
        return False
    return getattr(observation, "transport_mechanism", None) not in NON_RF_TRANSPORTS


def rf_observations(queryset):
    """Filter a PacketObservation queryset to radio observations; null via_mqtt/transport rows are kept."""
    return queryset.exclude(via_mqtt=True).exclude(transport_mechanism__in=NON_RF_TRANSPORTS)


def hops_unknown(hop_start: Optional[int], hop_limit: Optional[int], bitfield: Optional[int]) -> bool:
    """True when hop_start/hop_limit cannot tell us how far the packet travelled."""
    if hop_start is None or hop_limit is None:
        return True
    return hop_start == 0 and bitfield is None


def observation_hop_count(observation) -> Optional[int]:
    """Hops the packet travelled (hop_start - hop_limit), or None when unknown or inconsistent.

    A replayed observation (2.8 connect-time replay) has hop fields copied from the feeder, not from the air: None.
    So does a non-RF one (MQTT, UDP, API): its hops are not radio hops.
    """
    if getattr(observation, "replayed", False) or not observation_is_rf(observation):
        return None
    if hops_unknown(observation.hop_start, observation.hop_limit, getattr(observation, "bitfield", None)):
        return None
    hops = observation.hop_start - observation.hop_limit
    return hops if hops >= 0 else None


def observation_is_direct(observation) -> bool:
    """True when the packet was heard directly from the sender; False when direct is not known, replayed or non-RF."""
    if getattr(observation, "replayed", False) or not observation_is_rf(observation):
        return False
    return observation_hop_count(observation) == 0


def update_inferred_max_hops(node, observation, port_num) -> bool:
    """Update ``node``'s ``NodeLatestStatus.meshtastic_inferred_max_hops`` from an observation.

    Returns True when the stored value (with its ``_at`` and ``_source``) was written.
    """
    from nodes.models import NodeLatestStatus

    if getattr(observation, "replayed", False) or not observation_is_rf(observation):
        return False
    hop_start = getattr(observation, "hop_start", None) if observation else None
    hop_limit = getattr(observation, "hop_limit", None) if observation else None
    if hop_start is None:
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
