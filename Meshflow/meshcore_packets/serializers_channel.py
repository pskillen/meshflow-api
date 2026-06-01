"""Serializers for MeshCore channel sync and UI apply."""

from rest_framework import serializers

from constellations.models import MeshCoreChannelType, MessageChannel
from nodes.models import ManagedNodeMcChannelLink

# Wire/API strings (not gettext labels — lazy __proxy__ breaks Channels msgpack).
MC_CHANNEL_TYPE_API_CHOICES = [
    ("PUBLIC", "PUBLIC"),
    ("HASHTAG", "HASHTAG"),
]


class McChannelSnapshotEntrySerializer(serializers.Serializer):
    mc_channel_idx = serializers.IntegerField(min_value=0, max_value=63)
    name = serializers.CharField(max_length=100)
    mc_channel_type = serializers.ChoiceField(choices=MC_CHANNEL_TYPE_API_CHOICES)
    mc_hashtag = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)


class McChannelSyncSerializer(serializers.Serializer):
    channels = McChannelSnapshotEntrySerializer(many=True)
    synced_at = serializers.DateTimeField(required=False, allow_null=True)


class MessageChannelMcSerializer(serializers.ModelSerializer):
    """Canonical MessageChannel fields (no device index)."""

    mc_channel_type = serializers.SerializerMethodField()

    class Meta:
        model = MessageChannel
        fields = [
            "id",
            "name",
            "mc_channel_type",
            "mc_hashtag",
        ]

    def get_mc_channel_type(self, obj):
        if obj.mc_channel_type is None:
            return None
        return MeshCoreChannelType(obj.mc_channel_type).name


class FeederMcChannelMirrorSerializer(serializers.ModelSerializer):
    """Feeder device mirror: canonical channel plus slot index from the link row."""

    id = serializers.IntegerField(source="message_channel.id", read_only=True)
    name = serializers.CharField(source="message_channel.name", read_only=True)
    mc_channel_type = serializers.SerializerMethodField()
    mc_hashtag = serializers.CharField(
        source="message_channel.mc_hashtag",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ManagedNodeMcChannelLink
        fields = [
            "id",
            "name",
            "mc_channel_idx",
            "mc_channel_type",
            "mc_hashtag",
        ]

    def get_mc_channel_type(self, obj):
        ch = obj.message_channel
        if ch.mc_channel_type is None:
            return None
        return MeshCoreChannelType(ch.mc_channel_type).name


class McChannelApplyEntrySerializer(serializers.Serializer):
    mc_channel_idx = serializers.IntegerField(min_value=0, max_value=63, required=False)
    name = serializers.CharField(max_length=100)
    mc_channel_type = serializers.ChoiceField(choices=MC_CHANNEL_TYPE_API_CHOICES)
    mc_hashtag = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)


class McChannelApplySerializer(serializers.Serializer):
    channels = McChannelApplyEntrySerializer(many=True)

    def validate(self, attrs):
        channels = attrs.get("channels") or []
        for entry in channels:
            if str(entry.get("mc_channel_type")).upper() == "HASHTAG":
                tag = (entry.get("mc_hashtag") or entry.get("name") or "").strip().lstrip("#")
                if not tag:
                    raise serializers.ValidationError({"channels": "Hashtag channels require a non-empty hashtag."})
                entry["mc_hashtag"] = tag[:64]
                entry["name"] = tag[:100]
        return attrs
