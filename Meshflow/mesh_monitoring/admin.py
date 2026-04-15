from django.contrib import admin

from .models import NodePresence, NodeWatch


@admin.register(NodeWatch)
class NodeWatchAdmin(admin.ModelAdmin):
    list_display = ("user", "observed_node", "offline_after", "enabled", "created_at")
    list_filter = ("enabled",)
    raw_id_fields = ("user", "observed_node")


@admin.register(NodePresence)
class NodePresenceAdmin(admin.ModelAdmin):
    list_display = ("observed_node", "verification_started_at", "offline_confirmed_at")
    raw_id_fields = ("observed_node",)
