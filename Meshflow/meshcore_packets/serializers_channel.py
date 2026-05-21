"""Serializers for MeshCore channel sync and UI apply."""

from rest_framework import serializers

from constellations.models import MeshCoreChannelType, MessageChannel


class McChannelSnapshotEntrySerializer(serializers.Serializer):
    mc_channel_idx = serializers.IntegerField(min_value=0, max_value=63)
    name = serializers.CharField(max_length=100)
    mc_channel_type = serializers.ChoiceField(
        choices=[(c.label, c.label) for c in MeshCoreChannelType],
    )
    mc_hashtag = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)


class McChannelSyncSerializer(serializers.Serializer):
    channels = McChannelSnapshotEntrySerializer(many=True)
    synced_at = serializers.DateTimeField(required=False, allow_null=True)


class MessageChannelMcSerializer(serializers.ModelSerializer):
    mc_channel_type = serializers.SerializerMethodField()

    class Meta:
        model = MessageChannel
        fields = [
            "id",
            "name",
            "mc_channel_idx",
            "mc_channel_type",
            "mc_hashtag",
        ]

    def get_mc_channel_type(self, obj):
        if obj.mc_channel_type is None:
            return None
        return MeshCoreChannelType(obj.mc_channel_type).label


class McChannelApplyEntrySerializer(serializers.Serializer):
    mc_channel_idx = serializers.IntegerField(min_value=0, max_value=63, required=False)
    name = serializers.CharField(max_length=100)
    mc_channel_type = serializers.ChoiceField(
        choices=[(c.label, c.label) for c in MeshCoreChannelType],
    )
    mc_hashtag = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)


class McChannelApplySerializer(serializers.Serializer):
    channels = McChannelApplyEntrySerializer(many=True)

    def validate(self, attrs):
        channels = attrs.get("channels") or []
        for entry in channels:
            if entry.get("mc_channel_type") == MeshCoreChannelType.HASHTAG.label:
                tag = (entry.get("mc_hashtag") or entry.get("name") or "").strip().lstrip("#")
                if not tag:
                    raise serializers.ValidationError({"channels": "Hashtag channels require a non-empty hashtag."})
                entry["mc_hashtag"] = tag[:64]
                entry["name"] = tag[:100]
        return attrs
