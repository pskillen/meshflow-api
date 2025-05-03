from rest_framework import serializers

from .models import Constellation, ConstellationUserMembership, MessageChannel


class ConstellationSerializer(serializers.ModelSerializer):
    """Serializer for constellations."""

    channels = serializers.SerializerMethodField()

    class Meta:
        model = Constellation
        fields = ["id", "name", "description", "created_by", "channels"]
        read_only_fields = ["created_by"]

    def get_members(self, obj):
        memberships = ConstellationUserMembership.objects.filter(constellation=obj)
        return [{"username": membership.user.username, "role": membership.role} for membership in memberships]

    def get_channels(self, obj):
        channels = MessageChannel.objects.filter(constellation=obj)
        return [{"id": channel.id, "name": channel.name} for channel in channels]

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


class ConstellationMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = ConstellationUserMembership
        fields = ["user_id", "username", "role"]
