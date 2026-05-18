"""Django admin registration for Meshtastic packet models."""

from django.contrib import admin

from .models import MtRawPacket, PacketObservation


@admin.register(MtRawPacket)
class MtRawPacketAdmin(admin.ModelAdmin):
    """Read/write access to base Meshtastic raw packet rows (subclass rows use separate tables)."""

    list_display = ("id", "packet_id", "from_int", "from_str", "port_num", "first_reported_time")
    list_filter = ("port_num",)
    search_fields = ("packet_id", "from_str", "to_str")
    readonly_fields = ("id", "first_reported_time")


@admin.register(PacketObservation)
class PacketObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "packet", "observer", "rx_time", "upload_time")
    list_select_related = ("packet", "observer")
    raw_id_fields = ("packet", "observer", "channel")
