from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePacketObservation, MeshCoreRawPacket, MeshCoreTextPacket
from nodes.models import ManagedNode


class MeshCoreObserverFilter(admin.SimpleListFilter):
    """Filter packets/observations by feeder (ManagedNode)."""

    title = _("Observer feeder")
    parameter_name = "observer"

    def lookups(self, request, model_admin):
        qs = (
            ManagedNode.objects.filter(protocol=Protocol.MESHCORE, deleted_at__isnull=True)
            .select_related("constellation")
            .order_by("name")[:50]
        )
        return [(str(n.internal_id), f"{n.name} ({n.constellation.name})") for n in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(observer_id=self.value())
        return queryset


@admin.register(MeshCoreRawPacket)
class MeshCoreRawPacketAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "payload_type", "from_pubkey_prefix", "rx_time", "observer")
    list_filter = (
        "payload_type",
        "event_type",
        MeshCoreObserverFilter,
        "observer__constellation",
        ("from_pubkey", admin.EmptyFieldListFilter),
    )
    search_fields = ("from_pubkey", "from_pubkey_prefix", "observer__name")
    readonly_fields = ("id", "first_reported_time")
    list_select_related = ("observer", "observer__constellation")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("observer", "observer__constellation")


@admin.register(MeshCoreTextPacket)
class MeshCoreTextPacketAdmin(admin.ModelAdmin):
    list_display = ("id", "payload_type", "text", "channel", "rx_time", "observer")
    list_filter = ("payload_type", MeshCoreObserverFilter, "observer__constellation")
    search_fields = ("text", "observer__name")
    list_select_related = ("observer", "channel")


@admin.register(MeshCorePacketObservation)
class MeshCorePacketObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "packet", "observer", "rx_time", "upload_time")
    list_filter = (MeshCoreObserverFilter, "observer__constellation")
    list_select_related = ("packet", "observer", "observer__constellation")
    date_hierarchy = "upload_time"
