from django.contrib import admin

from .models import AutoTraceRoute


@admin.register(AutoTraceRoute)
class AutoTraceRouteAdmin(admin.ModelAdmin):
    list_display = ("source_node", "target_node", "trigger_type", "status", "triggered_at", "completed_at")
    list_filter = ("trigger_type", "status")
    search_fields = ("source_node__name", "target_node__short_name")
    readonly_fields = ("triggered_at", "completed_at")
    date_hierarchy = "triggered_at"
