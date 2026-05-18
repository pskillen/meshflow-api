from django.contrib import admin

from meshcore_packets.models import MeshCorePacketObservation, MeshCoreRawPacket, MeshCoreTextPacket


@admin.register(MeshCoreRawPacket)
class MeshCoreRawPacketAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "payload_type", "from_pubkey_prefix", "rx_time", "observer")
    list_filter = ("payload_type", "event_type")
    search_fields = ("from_pubkey", "from_pubkey_prefix")
    readonly_fields = ("id", "first_reported_time")


@admin.register(MeshCoreTextPacket)
class MeshCoreTextPacketAdmin(admin.ModelAdmin):
    list_display = ("id", "payload_type", "text", "channel", "rx_time")
    search_fields = ("text",)


@admin.register(MeshCorePacketObservation)
class MeshCorePacketObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "packet", "observer", "rx_time", "upload_time")
