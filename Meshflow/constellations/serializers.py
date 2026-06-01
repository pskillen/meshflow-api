from rest_framework import serializers

from common.mc_channel_labels import mc_channel_display_label
from common.protocol import Protocol
from constellations.models import Constellation, MeshCoreChannelType, MessageChannel


def message_channel_payload(channel: MessageChannel) -> dict:
    """Nested channel dict for Constellation list/detail (matches MessageChannel schema)."""
    mc_type = None
    if channel.mc_channel_type is not None:
        mc_type = MeshCoreChannelType(channel.mc_channel_type).label
    payload = {
        "id": channel.id,
        "name": channel.name,
        "protocol": channel.protocol,
        "mc_channel_type": mc_type,
        "mc_hashtag": channel.mc_hashtag,
        "constellation": channel.constellation_id,
    }
    if channel.protocol == Protocol.MESHCORE:
        payload["display_label"] = mc_channel_display_label(channel)
    return payload


class ConstellationSerializer(serializers.ModelSerializer):
    """Serializer for constellations."""

    channels = serializers.SerializerMethodField()

    class Meta:
        model = Constellation
        fields = [
            "id",
            "name",
            "description",
            "created_by",
            "channels",
            "map_color",
            "protocol",
            "bot_default_ignore_meshtastic_portnums",
            "bot_default_meshtastic_hop_limit",
        ]
        read_only_fields = ["created_by"]

    def get_channels(self, obj):
        channels = MessageChannel.objects.filter(constellation=obj).order_by("id")
        protocol_filter = self.context.get("channel_protocol_filter")
        if protocol_filter is not None:
            channels = channels.filter(protocol=protocol_filter)
        return [message_channel_payload(ch) for ch in channels]

    def create(self, validated_data):
        """Create a new constellation."""
        # Add the current user as the creator
        validated_data["created_by"] = self.context["request"].user

        # Create the constellation
        return super().create(validated_data)


class MessageChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageChannel
        fields = "__all__"
