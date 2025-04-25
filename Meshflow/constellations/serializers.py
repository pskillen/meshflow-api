from rest_framework import serializers

from .models import Constellation, ConstellationUserMembership


class ConstellationSerializer(serializers.ModelSerializer):
    """Serializer for constellations."""

    members = serializers.SerializerMethodField()

    class Meta:
        model = Constellation
        fields = ["id", "name", "description", "created_by", "members"]
        read_only_fields = ["created_by"]

    def get_members(self, obj):
        memberships = ConstellationUserMembership.objects.filter(constellation=obj)
        return [{"username": membership.user.username, "role": membership.role} for membership in memberships]

    def create(self, validated_data):
        """Create a new constellation."""
        # Add the current user as the creator
        validated_data["created_by"] = self.context["request"].user

        # Create the constellation
        return super().create(validated_data)
