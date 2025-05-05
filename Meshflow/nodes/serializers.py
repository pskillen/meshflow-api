import secrets

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation, ConstellationUserMembership
from users.models import User

from .models import (
    DeviceMetrics,
    LocationSource,
    ManagedNode,
    NodeAPIKey,
    NodeAuth,
    NodeOwnerClaim,
    ObservedNode,
    Position,
)


class NodeOwnerClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeOwnerClaim
        fields = ["node", "user", "claim_key", "created_at", "accepted_at"]
        read_only_fields = ["node", "user", "claim_key", "created_at", "accepted_at"]


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
            "owner",
            "last_used",
            "is_active",
        ]
        read_only_fields = ["id", "key", "created_at", "owner", "last_used"]

    def create(self, validated_data):
        """Create a new API key with a randomly generated key."""
        # Generate a random key
        key = secrets.token_hex(32)  # 64 character hex string

        # Add the key to the validated data
        validated_data["key"] = key

        # Add the current user as the owner
        validated_data["owner"] = self.context["request"].user

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

        # Add the current user as the owner
        user = self.context["request"].user
        validated_data["owner"] = user

        # Create the API key
        api_key = NodeAPIKey.objects.create(**validated_data)

        # Link the API key to nodes
        for node_id in nodes:
            try:
                node = ManagedNode.objects.get(node_id=node_id)
                NodeAuth.objects.create(api_key=api_key, node=node)
            except ManagedNode.DoesNotExist:
                # Skip nodes that don't exist
                pass

        return api_key


class ManagedNodeSerializer(serializers.ModelSerializer):
    """Serializer for managed nodes, enriched with observed node and latest position info."""

    class PositionSerializer(serializers.ModelSerializer):
        latitude = serializers.SerializerMethodField()
        longitude = serializers.SerializerMethodField()

        class Meta:
            model = Position
            fields = ["latitude", "longitude"]

        def get_latitude(self, obj):
            if hasattr(obj, "last_latitude") and obj.last_latitude:
                return obj.last_latitude
            return obj.default_location_latitude

        def get_longitude(self, obj):
            if hasattr(obj, "last_longitude") and obj.last_longitude:
                return obj.last_longitude
            return obj.default_location_longitude

    class UserSerializer(serializers.ModelSerializer):
        id = serializers.IntegerField(read_only=True)
        username = serializers.CharField(read_only=True)

        class Meta:
            model = User
            fields = ["id", "username"]

    class ConstellationSerializer(serializers.ModelSerializer):
        class Meta:
            model = Constellation
            fields = ["id", "name", "map_color"]

    long_name = serializers.SerializerMethodField()
    short_name = serializers.CharField(read_only=True)
    last_heard = serializers.DateTimeField(read_only=True)
    node_id_str = serializers.CharField(read_only=True)

    position = PositionSerializer(source="*", read_only=True)
    owner = UserSerializer(read_only=True)
    constellation = ConstellationSerializer(read_only=True)

    class Meta:
        model = ManagedNode
        fields = [
            "node_id",
            "name",
            "long_name",
            "short_name",
            "last_heard",
            "node_id_str",
            "owner",
            "constellation",
            "position",
        ]
        read_only_fields = [
            "internal_id",
            "long_name",
            "short_name",
            "last_heard",
            "node_id_str",
            "owner",
            "position",
            "constellation",
        ]

    def get_node_id_str(self, obj):
        # Use annotated value if present, else fallback to property
        if hasattr(obj, "node_id_str") and obj.node_id_str:
            return obj.node_id_str
        return meshtastic_id_to_hex(obj.node_id)

    def get_long_name(self, obj):
        if hasattr(obj, "long_name") and obj.long_name:
            return obj.long_name
        return obj.name


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
            "precision_bits",
            "ground_speed",
            "ground_track",
            "sats_in_view",
            "pdop",
        ]

    def to_internal_value(self, data):
        """Convert location source from string to integer and handle node field."""
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

        # Handle node field
        if "node" in data and isinstance(data["node"], ObservedNode):
            validated_data["node"] = data["node"]

        return validated_data


class DeviceMetricsSerializer(serializers.ModelSerializer):
    """Serializer for device metrics."""

    class Meta:
        model = DeviceMetrics
        fields = [
            "id",
            "node",
            "logged_time",
            "reported_time",
            "battery_level",
            "voltage",
            "channel_utilization",
            "air_util_tx",
            "uptime_seconds",
        ]


class ObservedNodeSerializer(serializers.ModelSerializer):
    """Serializer for observed nodes."""

    class OwnerSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ["id", "username"]

    node_id_str = serializers.CharField(read_only=True)

    latest_position = serializers.SerializerMethodField()
    latest_device_metrics = serializers.SerializerMethodField()

    owner = OwnerSerializer(source="claimed_by", read_only=True)

    def to_internal_value(self, data):
        """Convert node_id_str to node_id."""
        if "node_id" in data:
            data["node_id_str"] = meshtastic_id_to_hex(data["node_id"])
        return super().to_internal_value(data)

    class Meta:
        model = ObservedNode
        fields = [
            "internal_id",
            "node_id",
            "node_id_str",
            "mac_addr",
            "long_name",
            "short_name",
            "hw_model",
            "sw_version",
            "public_key",
            "role",
            "last_heard",
            "latest_position",
            "latest_device_metrics",
            "owner",
        ]
        read_only_fields = [
            "internal_id",
            "node_id_str",
            "last_heard",
            "role",
            "latest_position",
            "latest_device_metrics",
            "owner",
        ]

    def get_latest_position(self, obj):
        """Get the latest position for this node."""
        latest_position = Position.objects.filter(node=obj).order_by("-reported_time").first()
        if latest_position:
            return PositionSerializer(latest_position).data
        return None

    def get_latest_device_metrics(self, obj):
        """Get the latest device metrics for this node."""
        latest_metrics = DeviceMetrics.objects.filter(node=obj).order_by("-reported_time").first()
        if latest_metrics:
            return DeviceMetricsSerializer(latest_metrics).data
        return None


class ObservedNodeSearchSerializer(ObservedNodeSerializer):
    """Simplified serializer for observed nodes search results."""

    class Meta:
        model = ObservedNode
        fields = [
            "internal_id",
            "node_id",
            "node_id_str",
            "long_name",
            "short_name",
            "last_heard",
            "owner",
        ]
