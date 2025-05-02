from rest_framework import serializers
from .models import TextMessage
from nodes.models import ObservedNode
from constellations.models import MessageChannel

class TextMessageSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(queryset=ObservedNode.objects.all())
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())

    class Meta:
        model = TextMessage
        fields = [
            'id',
            'sender',
            'recipient_node_id',
            'channel',
            'sent_at',
            'message_text',
            'is_emoji',
            'reply_to_message_id',
        ]
        read_only_fields = ['id', 'sent_at'] 