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
    """Serializer for node owner claims with full node information."""

    class NodeSerializer(serializers.ModelSerializer):
        """Nested serializer for the node field."""

        class Meta:
            model = ObservedNode
            fields = ["node_id", "node_id_str", "long_name", "short_name", "last_heard"]
            read_only_fields = ["node_id", "node_id_str", "long_name", "short_name", "last_heard"]

    node = NodeSerializer(read_only=True)

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

    owner_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="owner", write_only=True, required=True
    )
    constellation_id = serializers.PrimaryKeyRelatedField(
        queryset=Constellation.objects.all(), source="constellation", write_only=True, required=True
    )
    owner = UserSerializer(read_only=True)
    constellation = ConstellationSerializer(read_only=True)

    long_name = serializers.SerializerMethodField()
    short_name = serializers.CharField(read_only=True)
    last_heard = serializers.DateTimeField(read_only=True)
    node_id_str = serializers.CharField(read_only=True)

    position = serializers.SerializerMethodField(read_only=True)
    device_metrics = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ManagedNode
        fields = [
            "node_id",
            "name",
            "long_name",
            "short_name",
            "last_heard",
            "node_id_str",
            "owner_id",
            "owner",
            "constellation_id",
            "constellation",
            "position",
            "device_metrics",
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
        # If annotated fields are present, build a dict for the serializer
        annotation_keys = [
            "last_latitude",
            "last_longitude",
            "last_altitude",
            "last_position_time",
            "last_heading",
            "last_location_source",
            "last_precision_bits",
            "last_ground_speed",
            "last_ground_track",
            "last_sats_in_view",
            "last_pdop",
        ]
        if any(hasattr(obj, k) for k in annotation_keys):
            data = {k: getattr(obj, k, None) for k in annotation_keys}
            data["node"] = getattr(obj, "internal_id", None)
            # Check if all real data fields are None
            real_fields = [
                "last_latitude",
                "last_longitude",
                "last_altitude",
                "last_position_time",
                "last_heading",
                "last_location_source",
                "last_precision_bits",
                "last_ground_speed",
                "last_ground_track",
                "last_sats_in_view",
                "last_pdop",
            ]
            if all(data[k] is None for k in real_fields):
                return None
            return PositionSerializer(data).data
        # Fallback to latest Position instance
        latest = Position.objects.filter(node__node_id=obj.node_id).order_by("-reported_time").first()
        return PositionSerializer(latest).data if latest else None

    def get_device_metrics(self, obj):
        annotation_keys = [
            "last_battery_level",
            "last_voltage",
            "last_metrics_time",
            "last_channel_utilization",
            "last_air_util_tx",
            "last_uptime_seconds",
        ]
        if any(hasattr(obj, k) for k in annotation_keys):
            data = {k: getattr(obj, k, None) for k in annotation_keys}
            data["node"] = getattr(obj, "internal_id", None)
            # Use the timestamp field as the indicator
            if data.get("last_metrics_time") is None:
                return None
            return DeviceMetricsSerializer(data).data
        latest = DeviceMetrics.objects.filter(node__node_id=obj.node_id).order_by("-reported_time").first()
        return DeviceMetricsSerializer(latest).data if latest else None

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
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
    """Serializer for position reports, supporting both model instances and dicts (from annotations)."""

    location_source = serializers.CharField(source="get_location_source_display", read_only=True)

    # Mapping from possible annotated keys to canonical field names
    ANNOTATION_MAP = {
        # For ObservedNode
        "latest_latitude": "latitude",
        "latest_longitude": "longitude",
        "latest_altitude": "altitude",
        "latest_position_time": "reported_time",
        "latest_heading": "heading",
        "latest_location_source": "location_source",
        "latest_precision_bits": "precision_bits",
        "latest_ground_speed": "ground_speed",
        "latest_ground_track": "ground_track",
        "latest_sats_in_view": "sats_in_view",
        "latest_pdop": "pdop",
        # For ManagedNode
        "last_latitude": "latitude",
        "last_longitude": "longitude",
        "last_altitude": "altitude",
        "last_position_time": "reported_time",
        "last_heading": "heading",
        "last_location_source": "location_source",
        "last_precision_bits": "precision_bits",
        "last_ground_speed": "ground_speed",
        "last_ground_track": "ground_track",
        "last_sats_in_view": "sats_in_view",
        "last_pdop": "pdop",
    }

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

    def to_representation(self, instance):
        # Support both model instance and dict/annotated object
        if isinstance(instance, dict):
            # Map annotated keys to canonical field names
            data = {}
            for field in self.Meta.fields:
                # Try direct field
                if field in instance:
                    data[field] = instance.get(field)
                else:
                    # Try annotation map
                    for ann_key, canon_key in self.ANNOTATION_MAP.items():
                        if canon_key == field and ann_key in instance:
                            data[field] = instance[ann_key]
                            break
                    else:
                        data[field] = None
            # location_source: try to get display value if possible
            if "location_source" in data and data["location_source"] is not None:
                try:
                    data["location_source"] = LocationSource(data["location_source"]).label
                except Exception:
                    pass
            return data
        return super().to_representation(instance)

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        # Convert location_source from string to integer using LocationSource
        if "location_source" in validated_data and validated_data["location_source"]:
            try:
                for source_choice in LocationSource:
                    if source_choice.label == validated_data["location_source"]:
                        validated_data["location_source"] = source_choice.value
                        break
                else:
                    validated_data["location_source"] = LocationSource.UNSET
            except (ValueError, TypeError):
                validated_data["location_source"] = LocationSource.UNSET
        # Handle node field
        if "node" in data and isinstance(data["node"], ObservedNode):
            validated_data["node"] = data["node"]
        return validated_data


class DeviceMetricsSerializer(serializers.ModelSerializer):
    """Serializer for device metrics, supporting both model instances and dicts (from annotations)."""

    ANNOTATION_MAP = {
        # For ObservedNode
        "latest_battery_level": "battery_level",
        "latest_voltage": "voltage",
        "latest_metrics_time": "reported_time",
        "latest_channel_utilization": "channel_utilization",
        "latest_air_util_tx": "air_util_tx",
        "latest_uptime_seconds": "uptime_seconds",
        # For ManagedNode
        "last_battery_level": "battery_level",
        "last_voltage": "voltage",
        "last_metrics_time": "reported_time",
        "last_channel_utilization": "channel_utilization",
        "last_air_util_tx": "air_util_tx",
        "last_uptime_seconds": "uptime_seconds",
    }

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

    def to_representation(self, instance):
        # Support both model instance and dict/annotated object
        if isinstance(instance, dict):
            data = {}
            for field in self.Meta.fields:
                if field in instance:
                    data[field] = instance.get(field)
                else:
                    for ann_key, canon_key in self.ANNOTATION_MAP.items():
                        if canon_key == field and ann_key in instance:
                            data[field] = instance[ann_key]
                            break
                    else:
                        data[field] = None
            return data
        return super().to_representation(instance)


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
        annotation_keys = [
            "latest_latitude",
            "latest_longitude",
            "latest_altitude",
            "latest_position_time",
            "latest_heading",
            "latest_location_source",
            "latest_precision_bits",
            "latest_ground_speed",
            "latest_ground_track",
            "latest_sats_in_view",
            "latest_pdop",
        ]
        if any(hasattr(obj, k) for k in annotation_keys):
            data = {k: getattr(obj, k, None) for k in annotation_keys}
            data["node"] = getattr(obj, "internal_id", None)
            real_fields = [
                "latest_latitude",
                "latest_longitude",
                "latest_altitude",
                "latest_position_time",
                "latest_heading",
                "latest_location_source",
                "latest_precision_bits",
                "latest_ground_speed",
                "latest_ground_track",
                "latest_sats_in_view",
                "latest_pdop",
            ]
            if all(data[k] is None for k in real_fields):
                return None
            return PositionSerializer(data).data
        latest = Position.objects.filter(node=obj).order_by("-reported_time").first()
        return PositionSerializer(latest).data if latest else None

    def get_latest_device_metrics(self, obj):
        annotation_keys = [
            "latest_battery_level",
            "latest_voltage",
            "latest_metrics_time",
            "latest_channel_utilization",
            "latest_air_util_tx",
            "latest_uptime_seconds",
        ]
        if any(hasattr(obj, k) for k in annotation_keys):
            data = {k: getattr(obj, k, None) for k in annotation_keys}
            data["node"] = getattr(obj, "internal_id", None)
            # Use the timestamp field as the indicator
            if data.get("latest_metrics_time") is None:
                return None
            return DeviceMetricsSerializer(data).data
        latest = DeviceMetrics.objects.filter(node=obj).order_by("-reported_time").first()
        return DeviceMetricsSerializer(latest).data if latest else None


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
