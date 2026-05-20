import logging

from django.dispatch import receiver

from mesh_monitoring.battery import evaluate_device_metrics_for_battery_alert
from packets.signals import device_metrics_recorded, node_last_heard_advanced

logger = logging.getLogger(__name__)


@receiver(device_metrics_recorded)
def on_device_metrics_recorded(sender, observed_node, battery_level, reported_time, device_metrics=None, **kwargs):
    try:
        evaluate_device_metrics_for_battery_alert(
            observed_node=observed_node,
            battery_level=float(battery_level),
            reported_time=reported_time,
            device_metrics=device_metrics,
        )
    except Exception:
        logger.exception("mesh_monitoring: battery evaluation failed for node %s", observed_node.node_id_str)


def on_auto_traceroute_completed_from_packet(sender, auto_tr, **kwargs):
    """Clear offline verification when a node-watch traceroute completes."""
    from mesh_monitoring.services import on_monitoring_traceroute_completed

    try:
        on_monitoring_traceroute_completed(auto_tr)
    except Exception:
        logger.exception("mesh_monitoring: monitor TR completion failed for auto_tr %s", auto_tr.id)


@receiver(node_last_heard_advanced)
def on_node_last_heard_advanced(sender, observed_node, last_heard=None, **kwargs):
    """Reset monitoring presence when any packet advances last_heard."""
    from mesh_monitoring.services import clear_presence_on_packet_from_node

    del last_heard
    try:
        clear_presence_on_packet_from_node(observed_node)
    except Exception:
        logger.exception(
            "mesh_monitoring: clear presence failed for node %s",
            observed_node.node_id_str,
        )
