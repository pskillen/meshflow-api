import secrets

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation, ConstellationUserMembership, MessageChannel
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
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    key = serializers.CharField(read_only=True)

    class Meta:
        model = NodeAPIKey
        fields = ["id", "name", "constellation", "nodes", "owner", "created_at", "last_used", "is_active", "key"]

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
            read_only_fields = ["username"]

    class ConstellationSerializer(serializers.ModelSerializer):
        class Meta:
            model = Constellation
            fields = ["id", "name", "map_color"]
            read_only_fields = ["name", "map_color"]

    # For write (POST/PUT), accept just the ID
    owner_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="owner", write_only=True, required=True
    )
    constellation_id = serializers.PrimaryKeyRelatedField(
        queryset=Constellation.objects.all(), source="constellation", write_only=True, required=True
    )
    # For read, show nested
    owner = UserSerializer(read_only=True)
    constellation = ConstellationSerializer(read_only=True)

    long_name = serializers.SerializerMethodField()
    short_name = serializers.CharField(read_only=True)
    last_heard = serializers.DateTimeField(read_only=True)
    node_id_str = serializers.CharField(read_only=True)

    position = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ManagedNode
        fields = [
            "node_id",
            "name",
            "long_name",
            "short_name",
            "last_heard",
            "node_id_str",
            "owner_id",  # for input
            "owner",  # for output
            "constellation_id",  # for input
            "constellation",  # for output
            "position",  # position is not a direct FK, so remove from input
        ]
        read_only_fields = [
            "internal_id",
            "long_name",
            "short_name",
            "last_heard",
            "node_id_str",
            "owner",
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

    def set_long_name(self, obj, value):
        if value:
            obj.name = value
            obj.save()

    def get_position(self, obj):
        # Keep your current read logic
        return self.PositionSerializer(obj).data

    def to_internal_value(self, data):
        # Let DRF do its normal validation first
        validated_data = super().to_internal_value(data)
        # Now handle position if present in input
        position = data.get("position")
        if position:
            lat = position.get("latitude")
            lon = position.get("longitude")
            if lat is not None:
                validated_data["default_location_latitude"] = lat
            if lon is not None:
                validated_data["default_location_longitude"] = lon
        return validated_data


class NestedChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageChannel
        fields = ["id", "name"]
        read_only_fields = ["name"]


class OwnedManagedNodeSerializer(ManagedNodeSerializer):
    """Serializer for managed nodes owned by the current user."""

    # For write
    channel_0 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_1 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_2 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_3 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_4 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_5 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_6 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )
    channel_7 = serializers.PrimaryKeyRelatedField(
        queryset=MessageChannel.objects.all(), required=False, allow_null=True
    )

    # For read, override to_representation
    # (or use a SerializerMethodField if you want to return the nested object)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Replace channel_0 with nested representation
        if instance.channel_0_id:
            rep["channel_0"] = NestedChannelSerializer(instance.channel_0).data
        else:
            rep["channel_0"] = None

        if instance.channel_1_id:
            rep["channel_1"] = NestedChannelSerializer(instance.channel_1).data
        else:
            rep["channel_1"] = None

        if instance.channel_2_id:
            rep["channel_2"] = NestedChannelSerializer(instance.channel_2).data
        else:
            rep["channel_2"] = None

        if instance.channel_3_id:
            rep["channel_3"] = NestedChannelSerializer(instance.channel_3).data
        else:
            rep["channel_3"] = None

        if instance.channel_4_id:
            rep["channel_4"] = NestedChannelSerializer(instance.channel_4).data
        else:
            rep["channel_4"] = None

        if instance.channel_5_id:
            rep["channel_5"] = NestedChannelSerializer(instance.channel_5).data
        else:
            rep["channel_5"] = None

        if instance.channel_6_id:
            rep["channel_6"] = NestedChannelSerializer(instance.channel_6).data
        else:
            rep["channel_6"] = None

        if instance.channel_7_id:
            rep["channel_7"] = NestedChannelSerializer(instance.channel_7).data
        else:
            rep["channel_7"] = None

        return rep

    class Meta:
        model = ManagedNode
        fields = ManagedNodeSerializer.Meta.fields + [
            "channel_0",
            "channel_1",
            "channel_2",
            "channel_3",
            "channel_4",
            "channel_5",
            "channel_6",
            "channel_7",
        ]


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
