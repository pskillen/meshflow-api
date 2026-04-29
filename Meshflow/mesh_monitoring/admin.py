from django.contrib import admin

from .models import NodeMonitoringConfig, NodePresence, NodeWatch


@admin.register(NodeWatch)
class NodeWatchAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "observed_node",
        "enabled",
        "offline_notifications_enabled",
        "battery_notifications_enabled",
        "created_at",
    )
    list_filter = ("enabled", "offline_notifications_enabled", "battery_notifications_enabled")
    raw_id_fields = ("user", "observed_node")


@admin.register(NodePresence)
class NodePresenceAdmin(admin.ModelAdmin):
    list_display = (
        "observed_node",
        "is_offline",
        "observed_online_at",
        "verification_started_at",
        "suspected_offline_at",
        "offline_confirmed_at",
        "last_tr_sent",
        "tr_sent_count",
        "last_zero_sources_at",
        "last_verification_notify_at",
        "battery_below_threshold_report_count",
        "battery_alert_confirmed_at",
    )
    raw_id_fields = ("observed_node",)


@admin.register(NodeMonitoringConfig)
class NodeMonitoringConfigAdmin(admin.ModelAdmin):
    list_display = (
        "observed_node",
        "last_heard_offline_after_seconds",
        "battery_alert_enabled",
        "battery_alert_threshold_percent",
        "battery_alert_report_count",
        "updated_at",
    )
    raw_id_fields = ("observed_node",)
