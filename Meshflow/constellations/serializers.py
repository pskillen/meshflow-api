from rest_framework import serializers

from .models import Constellation


class ConstellationSerializer(serializers.ModelSerializer):
    """Serializer for constellations."""

    class Meta:
        model = Constellation
        fields = ['id', 'name', 'description', 'created_by']
        read_only_fields = ['created_by']

    def create(self, validated_data):
        """Create a new constellation."""
        # Add the current user as the creator
        validated_data['created_by'] = self.context['request'].user

        # Create the constellation
        return super().create(validated_data)
