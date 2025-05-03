from rest_framework import serializers

from constellations.models import MessageChannel
from nodes.models import ObservedNode

from .models import TextMessage


class TextMessageSerializer(serializers.ModelSerializer):

    class ObservedNodeSerializer(serializers.ModelSerializer):
        class Meta:
            model = ObservedNode
            fields = ["node_id_str", "long_name", "short_name"]

    sender = ObservedNodeSerializer(read_only=True)
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())

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
        ]
