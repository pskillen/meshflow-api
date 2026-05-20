"""Dispatch receivers for packet post-processing signals."""

import logging

from django.dispatch import receiver

from packets.signals import packet_from_node_processed

logger = logging.getLogger(__name__)


def on_auto_traceroute_completed_from_packet(
    sender,
    auto_tr,
    traceroute_packet,
    packet_observation,
    observer=None,
    from_node=None,
    **kwargs,
):
    """DX detection and exploration follow-up after traceroute completion (order preserved)."""
    from dx_monitoring.exploration import on_auto_traceroute_exploration_finished
    from dx_monitoring.services import maybe_detect_dx_from_completed_traceroute

    maybe_detect_dx_from_completed_traceroute(auto_tr, traceroute_packet, packet_observation)
    on_auto_traceroute_exploration_finished(auto_tr)


@receiver(packet_from_node_processed)
def on_packet_from_node_processed(
    sender,
    packet,
    observer,
    observation,
    from_node,
    previous_last_heard=None,
    from_node_created=False,
    **kwargs,
):
    """Run DX candidate rules before ObservedNode.last_heard is updated."""
    from dx_monitoring.services import maybe_detect_dx_candidate

    try:
        maybe_detect_dx_candidate(
            packet=packet,
            observer=observer,
            observation=observation,
            from_node=from_node,
            previous_last_heard=previous_last_heard,
            from_node_created=from_node_created,
        )
    except Exception:
        logger.exception("dx_monitoring: candidate detection failed for packet %s", getattr(packet, "id", None))
