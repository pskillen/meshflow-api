from rest_framework import serializers

from common.protocol import Protocol
from nodes.models import ObservedNode
from text_messages.models import TextMessage


class ObservedNodeWSBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObservedNode
        fields = ["node_id_str", "long_name", "short_name"]


class TextMessageWSSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(format="hex", read_only=True)
    protocol = serializers.SerializerMethodField()
    sender = ObservedNodeWSBriefSerializer(read_only=True)
    channel = serializers.PrimaryKeyRelatedField(read_only=True)
    sent_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S.%fZ", read_only=True)
    original_packet_id = serializers.SerializerMethodField()
    original_mc_packet_id = serializers.SerializerMethodField()
    heard = serializers.SerializerMethodField()

    def get_protocol(self, obj):
        return Protocol(obj.protocol).label.lower()

    def get_original_mc_packet_id(self, obj):
        return str(obj.original_mc_packet_id) if obj.original_mc_packet_id else None

    class Meta:
        model = TextMessage
        fields = [
            "id",
            "protocol",
            "original_packet_id",
            "original_mc_packet_id",
            "sender",
            "recipient_meshtastic_node_id",
            "channel",
            "sent_at",
            "message_text",
            "is_emoji",
            "reply_to_meshtastic_packet_id",
            "heard",
        ]

    def get_original_packet_id(self, obj):
        return str(obj.original_packet_id) if obj.original_packet_id else None

    def get_heard(self, obj):
        if hasattr(obj.original_packet, "prefetched_observations"):
            from Meshflow.packets.serializers import PrefetchedPacketObservationSerializer

            observations = obj.original_packet.prefetched_observations
            return PrefetchedPacketObservationSerializer(observations, many=True, context=self.context).data
        return []
