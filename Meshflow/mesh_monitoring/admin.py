from django.contrib import admin

from .models import NodePresence, NodeWatch


@admin.register(NodeWatch)
class NodeWatchAdmin(admin.ModelAdmin):
    list_display = ("user", "observed_node", "offline_after", "enabled", "created_at")
    list_filter = ("enabled",)
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
    )
    raw_id_fields = ("observed_node",)
