"""Battery alert evaluation for mesh monitoring (driven by device metrics ingestion)."""

from django.db import transaction
from django.utils import timezone

from mesh_monitoring.models import NodeMonitoringConfig, NodePresence


def evaluate_device_metrics_for_battery_alert(
    *,
    observed_node,
    battery_level: float,
    reported_time,
    device_metrics=None,
    **_kwargs,
):
    """
    Update battery streak / alert episode on NodePresence and notify watchers when an episode is confirmed.

    Called from the ``device_metrics_recorded`` signal; must not import ``packets`` services.
    """
    del device_metrics, reported_time  # reserved for future use / logging

    cfg = NodeMonitoringConfig.objects.filter(pk=observed_node.pk).first()
    if cfg is None or not cfg.battery_alert_enabled:
        return

    threshold = float(cfg.battery_alert_threshold_percent)
    required = int(cfg.battery_alert_report_count)
    newly_confirmed = False
    presence_pk = None

    with transaction.atomic():
        presence, _ = NodePresence.objects.select_for_update().get_or_create(
            observed_node=observed_node,
            defaults={"is_offline": False},
        )
        presence_pk = presence.pk

        if battery_level >= threshold:
            presence.battery_below_threshold_report_count = 0
            presence.battery_alerting_since = None
            presence.battery_alert_confirmed_at = None
            presence.last_battery_recovered_at = timezone.now()
            presence.last_battery_alert_notify_at = None
            presence.save(
                update_fields=[
                    "battery_below_threshold_report_count",
                    "battery_alerting_since",
                    "battery_alert_confirmed_at",
                    "last_battery_recovered_at",
                    "last_battery_alert_notify_at",
                ],
            )
            return

        if presence.battery_below_threshold_report_count == 0:
            presence.battery_alerting_since = timezone.now()
        presence.battery_below_threshold_report_count += 1

        newly_confirmed = False
        if presence.battery_below_threshold_report_count >= required and presence.battery_alert_confirmed_at is None:
            presence.battery_alert_confirmed_at = timezone.now()
            newly_confirmed = True

        presence.save(
            update_fields=[
                "battery_below_threshold_report_count",
                "battery_alerting_since",
                "battery_alert_confirmed_at",
            ],
        )

    if newly_confirmed:
        from mesh_monitoring.services import notify_watchers_node_battery_low

        notify_watchers_node_battery_low(observed_node, battery_level, threshold, required)
        NodePresence.objects.filter(pk=presence_pk).update(last_battery_alert_notify_at=timezone.now())
