from rest_framework import serializers

from constellations.models import MessageChannel
from nodes.models import ObservedNode
from packets.models import MessagePacket, PacketObservation
from packets.serializers import PacketObservationSerializer

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
            "packet_id",
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
            "packet_id",
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
        """Get the list of nodes that heard this message."""
        try:
            # Find the MessagePacket for this TextMessage
            message_packet = MessagePacket.objects.get(packet_id=obj.packet_id)

            # Get all PacketObservation objects for this packet
            observations = PacketObservation.objects.filter(packet=message_packet)

            # Serialize the observations
            return PacketObservationSerializer(observations, many=True).data
        except MessagePacket.DoesNotExist:
            return []
