import logging

from django.dispatch import receiver

from mesh_monitoring.battery import evaluate_device_metrics_for_battery_alert
from packets.signals import device_metrics_recorded

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
