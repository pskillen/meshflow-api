import secrets

from rest_framework import serializers

from constellations.models import ConstellationUserMembership

from .models import LocationSource, NodeAPIKey, NodeAuth, Position


class APIKeySerializer(serializers.ModelSerializer):
    """Serializer for API keys."""

    class Meta:
        model = NodeAPIKey
        fields = [
            "id",
            "key",
            "name",
            "constellation",
            "created_at",
            "created_by",
            "last_used",
            "is_active",
        ]
        read_only_fields = ["id", "key", "created_at", "created_by", "last_used"]

    def create(self, validated_data):
        """Create a new API key with a randomly generated key."""
        # Generate a random key
        key = secrets.token_hex(32)  # 64 character hex string

        # Add the key to the validated data
        validated_data["key"] = key

        # Add the current user as the creator
        validated_data["created_by"] = self.context["request"].user

        # Create the API key
        return super().create(validated_data)


class APIKeyNodeSerializer(serializers.ModelSerializer):
    """Serializer for API key node links."""

    class Meta:
        model = NodeAuth
        fields = ["id", "api_key", "node"]


class APIKeyDetailSerializer(APIKeySerializer):
    """Serializer for API keys with node links."""

    nodes = serializers.SerializerMethodField()

    class Meta(APIKeySerializer.Meta):
        fields = APIKeySerializer.Meta.fields + ["nodes"]

    def get_nodes(self, obj):
        """Get the nodes linked to this API key."""
        return [link.node.node_id for link in obj.node_links.all()]


class APIKeyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating API keys."""

    nodes = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = NodeAPIKey
        fields = ["name", "constellation", "nodes"]

    def validate_constellation(self, value):
        """Validate that the user has permission to create API keys for this constellation."""
        user = self.context["request"].user

        # Check if the user is a member of the constellation with admin or editor role
        membership = ConstellationUserMembership.objects.filter(
            user=user, constellation=value, role__in=["admin", "editor"]
        ).first()

        if not membership:
            raise serializers.ValidationError("You don't have permission to create API keys for this constellation.")

        return value

    def create(self, validated_data):
        """Create a new API key with a randomly generated key and link it to nodes."""
        # Extract nodes from validated data
        nodes = validated_data.pop("nodes", [])

        # Generate a random key
        key = secrets.token_hex(32)  # 64 character hex string

        # Add the key to the validated data
        validated_data["key"] = key

        # Add the current user as the creator
        validated_data["created_by"] = self.context["request"].user

        # Create the API key
        api_key = NodeAPIKey.objects.create(**validated_data)

        # Link the API key to nodes
        from nodes.models import MeshtasticNode

        for node_id in nodes:
            try:
                node = MeshtasticNode.objects.get(node_id=node_id)
                NodeAuth.objects.create(api_key=api_key, node=node)
            except MeshtasticNode.DoesNotExist:
                # Skip nodes that don't exist
                pass

        return api_key


class PositionSerializer(serializers.ModelSerializer):
    """Serializer for position reports."""

    location_source = serializers.CharField(source="get_location_source_display", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "node",
            "logged_time",
            "reported_time",
            "latitude",
            "longitude",
            "altitude",
            "heading",
            "location_source",
        ]
        read_only_fields = ["id", "node", "logged_time", "reported_time"]

    def to_internal_value(self, data):
        """Convert location source from string to integer."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert location_source from string to integer using LocationSource
        if "location_source" in validated_data and validated_data["location_source"]:
            try:
                # Find the matching location source in LocationSource
                for source_choice in LocationSource:
                    if source_choice.label == validated_data["location_source"]:
                        validated_data["location_source"] = source_choice.value
                        break
                else:
                    # If no match found, set to UNSET
                    validated_data["location_source"] = LocationSource.UNSET
            except (ValueError, TypeError):
                validated_data["location_source"] = LocationSource.UNSET

        return validated_data
