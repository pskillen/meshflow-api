"""Serializers for the packets app."""

from django.utils import timezone

from rest_framework import serializers

from nodes.models import DeviceMetrics, ObservedNode, Position

from .models import (
    DeviceMetricsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    RoleSource,
)


class BasePacketSerializer(serializers.Serializer):
    """Base serializer for all packet types."""

    # Common fields from the JSON packet
    id = serializers.IntegerField(source="packet_id")
    from_int = serializers.IntegerField(source="from")
    from_str = serializers.CharField(source="fromId")
    to_int = serializers.IntegerField(source="to", required=False, allow_null=True)
    to_str = serializers.CharField(source="toId", required=False, allow_null=True)
    port_num = serializers.CharField(source="decoded.portnum")

    # Fields for PacketObservation
    channel = serializers.IntegerField(required=False, allow_null=True)
    hop_limit = serializers.IntegerField(
        source="hopLimit", required=False, allow_null=True
    )
    hop_start = serializers.IntegerField(
        source="hopStart", required=False, allow_null=True
    )
    rx_time = serializers.IntegerField(source="rxTime")
    rx_rssi = serializers.FloatField(source="rxRssi", required=False, allow_null=True)
    rx_snr = serializers.FloatField(source="rxSnr", required=False, allow_null=True)
    relay_node = serializers.IntegerField(
        source="relayNode", required=False, allow_null=True
    )

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert rxTime to a datetime object
        if "rx_time" in validated_data:
            validated_data["rx_time"] = timezone.datetime.fromtimestamp(
                validated_data["rx_time"], tz=timezone.utc
            )

        return validated_data


class MessagePacketSerializer(BasePacketSerializer):
    """Serializer for text message packets."""

    message_text = serializers.CharField(source="decoded.text")
    reply_packet_id = serializers.IntegerField(
        source="decoded.reply_id", required=False
    )
    emoji = serializers.IntegerField(
        source="decoded.emoji", required=False, allow_null=True
    )

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields and handle emoji conversion."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert rxTime to a datetime object
        if "rx_time" in validated_data:
            validated_data["rx_time"] = timezone.datetime.fromtimestamp(
                validated_data["rx_time"], tz=timezone.utc
            )

        # Convert emoji from int to boolean
        if "emoji" in validated_data:
            validated_data["emoji"] = bool(validated_data["emoji"])

        return validated_data

    def create(self, validated_data):
        """Create a new MessagePacket instance."""
        # Extract nested data
        decoded_data = validated_data.pop("decoded", {})

        # Create the packet
        packet = MessagePacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from"),
            from_str=validated_data.get("fromId"),
            to_int=validated_data.get("to"),
            to_str=validated_data.get("toId"),
            port_num=decoded_data.get("portnum"),
            message_text=decoded_data.get("text"),
            reply_packet_id=validated_data.get("reply_packet_id", 0),
            emoji=validated_data.get("emoji"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet

    def _create_observation(self, packet, validated_data):
        """Create a PacketObservation for the packet."""
        PacketObservation.objects.create(
            packet=packet,
            node=None,  # This would need to be set based on the node that received the packet
            channel=validated_data.get("channel"),
            hop_limit=validated_data.get("hopLimit"),
            hop_start=validated_data.get("hopStart"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rxRssi"),
            rx_snr=validated_data.get("rxSnr"),
            relay_node=validated_data.get("relayNode"),
        )


class PositionPacketSerializer(BasePacketSerializer):
    """Serializer for position packets."""

    latitude = serializers.FloatField(source="decoded.position.latitude")
    longitude = serializers.FloatField(source="decoded.position.longitude")
    altitude = serializers.FloatField(
        source="decoded.position.altitude", required=False, allow_null=True
    )
    heading = serializers.FloatField(
        source="decoded.position.heading", required=False, allow_null=True
    )
    location_source = serializers.CharField(
        source="decoded.position.locationSource", required=False, allow_null=True
    )
    precision_bits = serializers.IntegerField(
        source="decoded.position.precisionBits", required=False, allow_null=True
    )
    position_time = serializers.IntegerField(
        source="decoded.position.time", required=False, allow_null=True
    )
    ground_speed = serializers.FloatField(
        source="decoded.position.groundSpeed", required=False, allow_null=True
    )
    ground_track = serializers.FloatField(
        source="decoded.position.groundTrack", required=False, allow_null=True
    )

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields and handle timestamp and location source conversion."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert position_time to a datetime object
        if "position_time" in validated_data:
            validated_data["position_time"] = timezone.datetime.fromtimestamp(
                validated_data["position_time"], tz=timezone.utc
            )

        # Convert location_source from string to integer using LocationSource
        if "location_source" in validated_data and validated_data["location_source"]:
            try:
                # First try to convert directly to int if it's a numeric string
                try:
                    validated_data["location_source"] = int(
                        validated_data["location_source"]
                    )
                except (ValueError, TypeError):
                    # If not a number, look up the string value
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

    def create(self, validated_data):
        """Create a new PositionPacket instance."""
        # Extract nested data
        decoded_data = validated_data.pop("decoded", {})
        position_data = decoded_data.pop("position", {})

        # Create the packet
        packet = PositionPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from"),
            from_str=validated_data.get("fromId"),
            to_int=validated_data.get("to"),
            to_str=validated_data.get("toId"),
            port_num=decoded_data.get("portnum"),
            latitude=position_data.get("latitude"),
            longitude=position_data.get("longitude"),
            altitude=position_data.get("altitude"),
            heading=position_data.get("heading"),
            location_source=validated_data.get("location_source"),
            precision_bits=position_data.get("precisionBits"),
            position_time=validated_data.get("position_time"),
            ground_speed=position_data.get("groundSpeed"),
            ground_track=position_data.get("groundTrack"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet

    def _create_observation(self, packet, validated_data):
        """Create a PacketObservation for the packet."""
        PacketObservation.objects.create(
            packet=packet,
            node=None,  # This would need to be set based on the node that received the packet
            channel=validated_data.get("channel"),
            hop_limit=validated_data.get("hopLimit"),
            hop_start=validated_data.get("hopStart"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rxRssi"),
            rx_snr=validated_data.get("rxSnr"),
            relay_node=validated_data.get("relayNode"),
        )


class NodeInfoPacketSerializer(BasePacketSerializer):
    """Serializer for node info packets."""

    node_id = serializers.CharField(source="decoded.user.id")
    short_name = serializers.CharField(
        source="decoded.user.shortName", required=False, allow_null=True
    )
    long_name = serializers.CharField(
        source="decoded.user.longName", required=False, allow_null=True
    )
    hw_model = serializers.CharField(
        source="decoded.user.hwModel", required=False, allow_null=True
    )
    sw_version = serializers.CharField(
        source="decoded.user.swVersion", required=False, allow_null=True
    )
    public_key = serializers.CharField(
        source="decoded.user.publicKey", required=False, allow_null=True
    )
    mac_address = serializers.CharField(
        source="decoded.user.macaddr", required=False, allow_null=True
    )
    role = serializers.CharField(
        source="decoded.user.role", required=False, allow_null=True
    )

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields and handle role conversion."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert role from string to integer using RoleSource
        if "role" in validated_data and validated_data["role"]:
            try:
                # Find the matching role in RoleSource
                for role_choice in RoleSource:
                    if role_choice.label == validated_data["role"]:
                        validated_data["role"] = role_choice.value
                        break
                else:
                    # If no match found, set to None
                    validated_data["role"] = None
            except (ValueError, TypeError):
                validated_data["role"] = None

        return validated_data

    def create(self, validated_data):
        """Create a new NodeInfoPacket instance."""
        # Extract nested data
        decoded_data = validated_data.pop("decoded", {})
        user_data = decoded_data.pop("user", {})

        # Create the packet
        packet = NodeInfoPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from"),
            from_str=validated_data.get("fromId"),
            to_int=validated_data.get("to"),
            to_str=validated_data.get("toId"),
            port_num=decoded_data.get("portnum"),
            node_id=user_data.get("id"),
            short_name=user_data.get("shortName"),
            long_name=user_data.get("longName"),
            hw_model=user_data.get("hwModel"),
            sw_version=user_data.get("swVersion"),
            public_key=user_data.get("publicKey"),
            mac_address=user_data.get("macaddr"),
            role=validated_data.get("role"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet

    def _create_observation(self, packet, validated_data):
        """Create a PacketObservation for the packet."""
        PacketObservation.objects.create(
            packet=packet,
            node=None,  # This would need to be set based on the node that received the packet
            channel=validated_data.get("channel"),
            hop_limit=validated_data.get("hopLimit"),
            hop_start=validated_data.get("hopStart"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rxRssi"),
            rx_snr=validated_data.get("rxSnr"),
            relay_node=validated_data.get("relayNode"),
        )


class DeviceMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for device metrics packets."""

    battery_level = serializers.FloatField(
        source="decoded.telemetry.deviceMetrics.batteryLevel",
        required=False,
        allow_null=True,
    )
    voltage = serializers.FloatField(
        source="decoded.telemetry.deviceMetrics.voltage",
        required=False,
        allow_null=True,
    )
    channel_utilization = serializers.FloatField(
        source="decoded.telemetry.deviceMetrics.channelUtilization",
        required=False,
        allow_null=True,
    )
    air_util_tx = serializers.FloatField(
        source="decoded.telemetry.deviceMetrics.airUtilTx",
        required=False,
        allow_null=True,
    )
    uptime_seconds = serializers.IntegerField(
        source="decoded.telemetry.deviceMetrics.uptimeSeconds",
        required=False,
        allow_null=True,
    )
    reading_time = serializers.IntegerField(source="decoded.telemetry.time")

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields."""
        # First, handle the standard conversion
        validated_data = super().to_internal_value(data)

        # Convert reading_time to a datetime object
        if "reading_time" in validated_data:
            validated_data["reading_time"] = timezone.datetime.fromtimestamp(
                validated_data["reading_time"], tz=timezone.utc
            )

        return validated_data

    def create(self, validated_data):
        """Create a new DeviceMetricsPacket instance."""
        # Extract nested data
        decoded_data = validated_data.pop("decoded", {})
        telemetry_data = decoded_data.pop("telemetry", {})
        device_metrics_data = telemetry_data.pop("deviceMetrics", {})

        # Create the packet
        packet = DeviceMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from"),
            from_str=validated_data.get("fromId"),
            to_int=validated_data.get("to"),
            to_str=validated_data.get("toId"),
            port_num=decoded_data.get("portnum"),
            reading_time=validated_data.get("reading_time"),
            battery_level=device_metrics_data.get("batteryLevel"),
            voltage=device_metrics_data.get("voltage"),
            channel_utilization=device_metrics_data.get("channelUtilization"),
            air_util_tx=device_metrics_data.get("airUtilTx"),
            uptime_seconds=device_metrics_data.get("uptimeSeconds"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet

    def _create_observation(self, packet, validated_data):
        """Create a PacketObservation for the packet."""
        PacketObservation.objects.create(
            packet=packet,
            node=None,  # This would need to be set based on the node that received the packet
            channel=validated_data.get("channel"),
            hop_limit=validated_data.get("hopLimit"),
            hop_start=validated_data.get("hopStart"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rxRssi"),
            rx_snr=validated_data.get("rxSnr"),
            relay_node=validated_data.get("relayNode"),
        )


class PacketIngestSerializer(serializers.Serializer):
    """Serializer for ingesting packets of any type."""

    def to_internal_value(self, data):
        """Determine the packet type and use the appropriate serializer."""
        # Check if the required fields are present
        if "decoded" not in data or "portnum" not in data["decoded"]:
            raise serializers.ValidationError({"decoded": "Missing 'portnum' field"})

        # Determine the packet type based on the portnum
        port_num = data["decoded"]["portnum"]

        # Use the appropriate serializer based on the port_num
        if port_num == "TEXT_MESSAGE_APP":
            serializer = MessagePacketSerializer(data=data)
        elif port_num == "POSITION_APP":
            serializer = PositionPacketSerializer(data=data)
        elif port_num == "NODEINFO_APP":
            serializer = NodeInfoPacketSerializer(data=data)
        elif port_num == "TELEMETRY_APP":
            # Check if it's a device metrics packet
            if (
                "telemetry" in data["decoded"]
                and "deviceMetrics" in data["decoded"]["telemetry"]
            ):
                serializer = DeviceMetricsPacketSerializer(data=data)
            else:
                # Handle other telemetry types if needed
                raise serializers.ValidationError(
                    {"decoded": "Unsupported telemetry type"}
                )
        else:
            # Handle other packet types or raise an error
            raise serializers.ValidationError(
                {"decoded": f"Unsupported packet type: {port_num}"}
            )

        # Validate the data using the selected serializer
        if serializer.is_valid(raise_exception=True):
            return serializer.validated_data

        return {}

    def create(self, validated_data):
        """Create a new packet instance based on the packet type."""
        # Determine the packet type based on the portnum
        port_num = validated_data["decoded"]["portnum"]

        # Use the appropriate serializer based on the port_num
        if port_num == "TEXT_MESSAGE_APP":
            serializer = MessagePacketSerializer()
        elif port_num == "POSITION_APP":
            serializer = PositionPacketSerializer()
        elif port_num == "NODEINFO_APP":
            serializer = NodeInfoPacketSerializer()
        elif port_num == "TELEMETRY_APP":
            # Check if it's a device metrics packet
            if (
                "telemetry" in validated_data["decoded"]
                and "deviceMetrics" in validated_data["decoded"]["telemetry"]
            ):
                serializer = DeviceMetricsPacketSerializer()
            else:
                # Handle other telemetry types if needed
                raise serializers.ValidationError(
                    {"decoded": "Unsupported telemetry type"}
                )
        else:
            # Handle other packet types or raise an error
            raise serializers.ValidationError(
                {"decoded": f"Unsupported packet type: {port_num}"}
            )

        # Create the packet using the selected serializer
        return serializer.create(validated_data)


class PositionSerializer(serializers.Serializer):
    logged_time = serializers.DateTimeField(default=timezone.now)
    reported_time = serializers.DateTimeField(required=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    altitude = serializers.FloatField()
    heading = serializers.FloatField()
    location_source = serializers.CharField()

    def to_internal_value(self, data):
        """Convert location source from string to integer."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # Convert location_source from string to integer using LocationSource
        if "location_source" in validated_data and validated_data["location_source"]:
            try:
                # First try to convert directly to int if it's a numeric string
                try:
                    validated_data["location_source"] = int(
                        validated_data["location_source"]
                    )
                except (ValueError, TypeError):
                    # If not a number, look up the string value
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


class DeviceMetricsSerializer(serializers.Serializer):
    logged_time = serializers.DateTimeField(default=timezone.now)
    reported_time = serializers.DateTimeField(required=True)
    battery_level = serializers.FloatField()
    voltage = serializers.FloatField()
    channel_utilization = serializers.FloatField()
    air_util_tx = serializers.FloatField()
    uptime_seconds = serializers.IntegerField()


class NodeSerializer(serializers.ModelSerializer):
    position = PositionSerializer(required=False, allow_null=True, write_only=True)
    device_metrics = DeviceMetricsSerializer(
        required=False, allow_null=True, write_only=True
    )
    id = serializers.IntegerField(source="node_id")
    macaddr = serializers.CharField(source="mac_addr")
    long_name = serializers.CharField(required=False)
    short_name = serializers.CharField(required=False)

    class Meta:
        model = ObservedNode
        fields = [
            "id",
            "macaddr",
            "long_name",
            "short_name",
            "hw_model",
            "sw_version",
            "public_key",
            "position",
            "device_metrics",
        ]

    def to_internal_value(self, data):
        # Handle the nested user data
        if "user" in data:
            user_data = data.pop("user")
            data["long_name"] = user_data.get("long_name")
            data["short_name"] = user_data.get("short_name")
        return super().to_internal_value(data)

    def create(self, validated_data):
        # Handle position data
        position_data = validated_data.pop("position", None)
        device_metrics_data = validated_data.pop("device_metrics", None)

        # Map macaddr to mac_addr
        if "macaddr" in validated_data:
            validated_data["mac_addr"] = validated_data.pop("macaddr")

        # Create the node
        node = ObservedNode.objects.create(**validated_data)

        # Handle position data if present
        if position_data:
            # Create position record
            Position.objects.create(
                node=node,
                logged_time=position_data.get("logged_time", timezone.now()),
                reported_time=position_data.get("reported_time"),
                latitude=position_data.get("latitude"),
                longitude=position_data.get("longitude"),
                altitude=position_data.get("altitude"),
                location_source=position_data.get("location_source"),
            )

        # Handle device metrics data if present
        if device_metrics_data:
            # Create device metrics record
            DeviceMetrics.objects.create(
                node=node,
                logged_time=device_metrics_data.get("logged_time", timezone.now()),
                reported_time=device_metrics_data.get("reported_time"),
                battery_level=device_metrics_data.get("battery_level"),
                voltage=device_metrics_data.get("voltage"),
                channel_utilization=device_metrics_data.get("channel_utilization"),
                air_util_tx=device_metrics_data.get("air_util_tx"),
                uptime_seconds=device_metrics_data.get("uptime_seconds"),
            )

        return node

    def update(self, instance, validated_data):
        # Handle position data
        position_data = validated_data.pop("position", None)
        if position_data:
            instance.position_logged_time = position_data.get(
                "logged_time", timezone.now()
            )
            instance.position_reported_time = position_data.get("reported_time")
            instance.latitude = position_data.get("latitude")
            instance.longitude = position_data.get("longitude")
            instance.altitude = position_data.get("altitude")
            instance.location_source = position_data.get("location_source")

        # Handle device metrics data
        device_metrics_data = validated_data.pop("device_metrics", None)
        if device_metrics_data:
            instance.device_metrics_logged_time = device_metrics_data.get(
                "logged_time", timezone.now()
            )
            instance.battery_level = device_metrics_data.get("battery_level")
            instance.voltage = device_metrics_data.get("voltage")
            instance.channel_utilization = device_metrics_data.get(
                "channel_utilization"
            )
            instance.air_util_tx = device_metrics_data.get("air_util_tx")
            instance.uptime_seconds = device_metrics_data.get("uptime_seconds")

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance
