from django.contrib import admin

from dx_monitoring.models import (
    DxEvent,
    DxEventObservation,
    DxEventTraceroute,
    DxNodeMetadata,
    DxNotificationCategorySelection,
    DxNotificationDelivery,
    DxNotificationSubscription,
)


class DxEventObservationInline(admin.TabularInline):
    model = DxEventObservation
    extra = 0
    readonly_fields = ("id", "raw_packet", "packet_observation", "observer", "observed_at", "distance_km", "metadata")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DxEvent)
class DxEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "constellation",
        "destination",
        "reason_code",
        "state",
        "first_observed_at",
        "last_observed_at",
        "active_until",
        "observation_count",
        "last_observer",
        "best_distance_km",
    )
    list_filter = ("reason_code", "state", "constellation")
    search_fields = ("destination__node_id_str", "destination__long_name")
    readonly_fields = ("id", "metadata")
    inlines = [DxEventObservationInline]


@admin.register(DxEventObservation)
class DxEventObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "observer", "observed_at", "distance_km")
    list_filter = ("observer__constellation",)
    search_fields = ("event__destination__node_id_str",)
    readonly_fields = ("id", "metadata")


@admin.register(DxEventTraceroute)
class DxEventTracerouteAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "source_node", "outcome", "skip_reason", "auto_traceroute", "created_at")
    list_filter = ("outcome", "skip_reason")
    search_fields = ("event__destination__node_id_str",)
    readonly_fields = ("id", "metadata", "created_at", "updated_at")


@admin.register(DxNodeMetadata)
class DxNodeMetadataAdmin(admin.ModelAdmin):
    list_display = ("observed_node", "exclude_from_detection", "cluster_position_evaluated_for_dx", "updated_at")
    list_filter = ("exclude_from_detection", "cluster_position_evaluated_for_dx")
    search_fields = ("observed_node__node_id_str", "exclude_notes")


class DxNotificationCategorySelectionInline(admin.TabularInline):
    model = DxNotificationCategorySelection
    extra = 0


@admin.register(DxNotificationSubscription)
class DxNotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "enabled", "all_categories", "updated_at")
    list_filter = ("enabled", "all_categories")
    search_fields = ("user__username", "user__email")
    inlines = [DxNotificationCategorySelectionInline]


@admin.register(DxNotificationDelivery)
class DxNotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "user", "category", "created_at")
    list_filter = ("category",)
    search_fields = ("user__username", "event__id")
    readonly_fields = ("id", "event", "user", "category", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
