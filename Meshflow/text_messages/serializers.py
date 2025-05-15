from rest_framework import serializers

from constellations.models import MessageChannel
from nodes.models import ObservedNode
from packets.serializers import PrefetchedPacketObservationSerializer

from .models import TextMessage


class TextMessageSerializer(serializers.ModelSerializer):

    class ObservedNodeSerializer(serializers.ModelSerializer):
        class Meta:
            model = ObservedNode
            fields = ["node_id_str", "long_name", "short_name"]

    sender = ObservedNodeSerializer(read_only=True)
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())
    heard = serializers.SerializerMethodField()

    class Meta:
        model = TextMessage
        fields = [
            "id",
            "original_packet_id",
            "sender",
            "recipient_node_id",
            "channel",
            "sent_at",
            "message_text",
            "is_emoji",
            "reply_to_message_id",
            "heard",
        ]
        # all fields are read-only (must be a list or tuple)
        read_only_fields = [
            "id",
            "original_packet_id",
            "sender",
            "recipient_node_id",
            "channel",
            "sent_at",
            "message_text",
            "is_emoji",
            "reply_to_message_id",
            "heard",
        ]

    def get_heard(self, obj):
        # Use prefetched observations if available
        if hasattr(obj.original_packet, "prefetched_observations"):
            observations = obj.original_packet.prefetched_observations
            return PrefetchedPacketObservationSerializer(observations, many=True, context=self.context).data
        return []
