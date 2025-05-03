from rest_framework import serializers

from constellations.models import MessageChannel
from nodes.models import ObservedNode

from .models import TextMessage


class TextMessageSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(queryset=ObservedNode.objects.all())
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
        # all fields are read-only
        read_only_fields = "__all__"
