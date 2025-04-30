"""Serializers for the packets app."""

from datetime import datetime, timezone

from django.utils import timezone as django_timezone

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_hex_to_int, meshtastic_id_to_hex
from nodes.models import DeviceMetrics, ObservedNode, Position

from .models import (
    DeviceMetricsPacket,
    LocalStatsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    RoleSource,
)


def convert_timestamp(timestamp):
    """Convert a Unix timestamp to a datetime object."""
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, TypeError, OSError) as e:
        raise serializers.ValidationError({"timestamp": f"Invalid timestamp: {str(e)}"})


def convert_location_source(source):
    """Convert a location source string to its integer value."""
    if not source:
        return LocationSource.UNSET

    try:
        # Try to convert directly to int if it's a numeric string
        return int(source)
    except (ValueError, TypeError):
        # If not a number, look up the string value
        for source_choice in LocationSource:
            if source_choice.label == source:
                return source_choice.value
        # If no match found, set to UNSET
        return LocationSource.UNSET


class BasePacketSerializer(serializers.Serializer):
    """Base serializer for all packet types."""

    # Common fields from the JSON packet
    id = serializers.IntegerField(source="packet_id")
    # 'from' is a reserved word in Python, so we use vars() to access it
    vars()["from"] = serializers.IntegerField(source="from_int", required=True, allow_null=False)
    fromId = serializers.CharField(source="from_str", required=False, allow_null=True)
    to = serializers.IntegerField(source="to_int", required=False, allow_null=True)
    toId = serializers.CharField(source="to_str", required=False, allow_null=True)
    decoded = serializers.JSONField()  # Will be overridden by child classes
    portnum = serializers.CharField(source="port_num", read_only=True)

    # Fields for PacketObservation
    channel = serializers.IntegerField(required=False, allow_null=True)
    hopLimit = serializers.IntegerField(source="hop_limit", required=False, allow_null=True)
    hopStart = serializers.IntegerField(source="hop_start", required=False, allow_null=True)
    rxTime = serializers.IntegerField(source="rx_time")
    rxRssi = serializers.FloatField(source="rx_rssi", required=False, allow_null=True)
    rxSnr = serializers.FloatField(source="rx_snr", required=False, allow_null=True)
    relayNode = serializers.IntegerField(source="relay_node", required=False, allow_null=True)

    # Additional fields from OpenAPI spec
    pkiEncrypted = serializers.BooleanField(source="pki_encrypted", required=False, allow_null=True)
    nextHop = serializers.IntegerField(source="next_hop", required=False, allow_null=True)
    priority = serializers.CharField(required=False, allow_null=True)
    raw = serializers.CharField(required=False)

    def to_internal_value(self, data):
        """Convert camelCase to snake_case for nested fields."""
        # First, handle the standard DRF conversion
        validated_data = super().to_internal_value(data)

        # override the hex node_id with the integer node_id
        if "from" in validated_data:
            from_int = validated_data["from_int"]
            from_str = meshtastic_id_to_hex(from_int)
            validated_data["from_str"] = from_str
        if "to" in validated_data:
            to_int = validated_data["to_int"]
            to_str = meshtastic_id_to_hex(to_int)
            validated_data["to_str"] = to_str

        # Extract portnum from decoded structure
        if "decoded" in data and "portnum" in data["decoded"]:
            validated_data["port_num"] = data["decoded"]["portnum"]

        # Convert rxTime to a datetime object with validation
        if "rx_time" in validated_data:
            validated_data["rx_time"] = convert_timestamp(validated_data["rx_time"])

        return validated_data

    def _create_observation(self, packet, validated_data):
        """Create a PacketObservation for the packet."""
        # Get the observer from the request context
        observer = self.context.get("observer")
        if not observer:
            raise serializers.ValidationError("No observer found in request context")

        PacketObservation.objects.create(
            packet=packet,
            observer=observer,
            channel=validated_data.get("channel"),
            hop_limit=validated_data.get("hop_limit"),
            hop_start=validated_data.get("hop_start"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rx_rssi"),
            rx_snr=validated_data.get("rx_snr"),
            relay_node=validated_data.get("relay_node"),
        )

        # Update the last_heard field of the ObservedNode that sent the packet
        if "from_int" in validated_data and validated_data.get("rx_time"):
            try:
                node = ObservedNode.objects.get(node_id=validated_data.get("from_int"))
                node.last_heard = validated_data.get("rx_time")
                node.save(update_fields=["last_heard"])
            except ObservedNode.DoesNotExist:
                # If the node doesn't exist, we don't need to update it
                pass


class MessagePacketSerializer(BasePacketSerializer):
    """Serializer for text message packets."""

    class DecodedSerializer(serializers.Serializer):
        """Serializer for message packet decoded data."""

        text = serializers.CharField(source="message_text")
        replyId = serializers.IntegerField(source="reply_packet_id", required=False)
        emoji = serializers.IntegerField(required=False, allow_null=True)

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        """Flatten decoded data and convert emoji from int to boolean."""
        validated_data = super().to_internal_value(data)

        # Flatten the decoded data
        if "decoded" in validated_data:
            decoded_data = validated_data.pop("decoded")
            validated_data.update(decoded_data)

        # Convert emoji from int to boolean
        if "emoji" in validated_data:
            validated_data["emoji"] = bool(validated_data["emoji"])

        return validated_data

    def create(self, validated_data):
        """Create a new MessagePacket instance."""

        # Create the packet
        packet = MessagePacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            message_text=validated_data.get("message_text"),
            reply_packet_id=validated_data.get("reply_packet_id"),
            emoji=validated_data.get("emoji", False),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class PositionPacketSerializer(BasePacketSerializer):
    """Serializer for position packets."""

    class DecodedSerializer(serializers.Serializer):
        """Serializer for position packet decoded data."""

        class PositionSerializer(serializers.Serializer):
            latitude = serializers.FloatField()
            longitude = serializers.FloatField()
            altitude = serializers.FloatField(required=False, allow_null=True)
            heading = serializers.FloatField(required=False, allow_null=True)
            locationSource = serializers.CharField(source="location_source", required=False, allow_null=True)
            precisionBits = serializers.IntegerField(source="precision_bits", required=False, allow_null=True)
            time = serializers.IntegerField(source="position_time", required=False, allow_null=True)
            groundSpeed = serializers.FloatField(source="ground_speed", required=False, allow_null=True)
            groundTrack = serializers.FloatField(source="ground_track", required=False, allow_null=True)

        position = PositionSerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        """Handle timestamp and location source conversion, and flatten nested data."""
        validated_data = super().to_internal_value(data)

        # Flatten the nested position data
        if "position" in validated_data:
            position_data = validated_data.pop("position")
            validated_data.update(position_data)

        # Convert position_time to a datetime object if it exists
        if "position_time" in validated_data and validated_data["position_time"] is not None:
            validated_data["position_time"] = convert_timestamp(validated_data["position_time"])

        # Convert location_source from string to integer using LocationSource
        if "location_source" in validated_data and validated_data["location_source"]:
            validated_data["location_source"] = convert_location_source(validated_data["location_source"])

        return validated_data

    def create(self, validated_data):
        """Create a new PositionPacket instance."""

        # Create the packet
        packet = PositionPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            latitude=validated_data.get("latitude"),
            longitude=validated_data.get("longitude"),
            altitude=validated_data.get("altitude"),
            heading=validated_data.get("heading"),
            location_source=validated_data.get("location_source"),
            precision_bits=validated_data.get("precision_bits"),
            position_time=validated_data.get("position_time"),
            ground_speed=validated_data.get("ground_speed"),
            ground_track=validated_data.get("ground_track"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class NodeInfoPacketSerializer(BasePacketSerializer):
    """Serializer for node info packets."""

    class DecodedSerializer(serializers.Serializer):
        """Serializer for node info packet decoded data."""

        class UserSerializer(serializers.Serializer):
            id = serializers.CharField(source="node_id")
            shortName = serializers.CharField(source="short_name", required=False, allow_null=True)
            longName = serializers.CharField(source="long_name", required=False, allow_null=True)
            hwModel = serializers.CharField(source="hw_model", required=False, allow_null=True, allow_blank=True)
            swVersion = serializers.CharField(source="sw_version", required=False, allow_null=True, allow_blank=True)
            publicKey = serializers.CharField(source="public_key", required=False, allow_null=True, allow_blank=True)
            macaddr = serializers.CharField(source="mac_address", required=False, allow_null=True)
            role = serializers.CharField(required=False, allow_null=True)

        user = UserSerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        """Handle role conversion and flatten nested user data."""
        validated_data = super().to_internal_value(data)

        # Flatten the nested user data
        if "user" in validated_data:
            user_data = validated_data.pop("user")
            validated_data.update(user_data)

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

        # Create the packet
        packet = NodeInfoPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            node_id=validated_data.get("node_id"),
            short_name=validated_data.get("short_name"),
            long_name=validated_data.get("long_name"),
            hw_model=validated_data.get("hw_model"),
            sw_version=validated_data.get("sw_version"),
            public_key=validated_data.get("public_key"),
            mac_address=validated_data.get("mac_address"),
            role=validated_data.get("role"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class DeviceMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for device metrics packets."""

    class DecodedSerializer(serializers.Serializer):
        """Serializer for device metrics packet decoded data."""

        class TelemetrySerializer(serializers.Serializer):
            class DeviceMetricsSerializer(serializers.Serializer):
                batteryLevel = serializers.FloatField(source="battery_level", required=False, allow_null=True)
                voltage = serializers.FloatField(required=False, allow_null=True)
                channelUtilization = serializers.FloatField(
                    source="channel_utilization", required=False, allow_null=True
                )
                airUtilTx = serializers.FloatField(source="air_util_tx", required=False, allow_null=True)
                uptimeSeconds = serializers.IntegerField(source="uptime_seconds", required=False, allow_null=True)

            deviceMetrics = DeviceMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        """Handle timestamp conversion and flatten nested data."""
        validated_data = super().to_internal_value(data)

        # Flatten the nested telemetry and device metrics data
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "deviceMetrics" in telemetry_data:
                device_metrics_data = telemetry_data.pop("deviceMetrics")
                validated_data.update(device_metrics_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]

            # add the rest of the telemetry data
            validated_data.update(telemetry_data)

        # Convert reading_time to a datetime object
        if "reading_time" in validated_data:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])

        return validated_data

    def create(self, validated_data):
        """Create a new DeviceMetricsPacket instance."""

        # Create the packet
        packet = DeviceMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            battery_level=validated_data.get("battery_level"),
            voltage=validated_data.get("voltage"),
            channel_utilization=validated_data.get("channel_utilization"),
            air_util_tx=validated_data.get("air_util_tx"),
            uptime_seconds=validated_data.get("uptime_seconds"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class LocalStatsPacketSerializer(BasePacketSerializer):
    """Serializer for local stats telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        """Serializer for local stats packet decoded data."""

        class TelemetrySerializer(serializers.Serializer):
            class LocalStatsSerializer(serializers.Serializer):
                uptimeSeconds = serializers.IntegerField(source="uptime_seconds", required=False, allow_null=True)
                channelUtilization = serializers.FloatField(
                    source="channel_utilization", required=False, allow_null=True
                )
                airUtilTx = serializers.FloatField(source="air_util_tx", required=False, allow_null=True)
                numPacketsTx = serializers.IntegerField(source="num_packets_tx", required=False, allow_null=True)
                numPacketsRx = serializers.IntegerField(source="num_packets_rx", required=False, allow_null=True)
                numPacketsRxBad = serializers.IntegerField(source="num_packets_rx_bad", required=False, allow_null=True)
                numOnlineNodes = serializers.IntegerField(source="num_online_nodes", required=False, allow_null=True)
                numTotalNodes = serializers.IntegerField(source="num_total_nodes", required=False, allow_null=True)
                numRxDupe = serializers.IntegerField(source="num_rx_dupe", required=False, allow_null=True)

            localStats = LocalStatsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        """Handle timestamp conversion and flatten nested data."""
        validated_data = super().to_internal_value(data)

        # Flatten the nested telemetry and local stats data
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "localStats" in telemetry_data:
                local_stats_data = telemetry_data.pop("localStats")
                validated_data.update(local_stats_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]

            # add the rest of the telemetry data
            validated_data.update(telemetry_data)

        # Convert reading_time to a datetime object if it exists
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])

        return validated_data

    def create(self, validated_data):
        """Create a new LocalStatsPacket instance."""

        # Create the packet
        packet = LocalStatsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            uptime_seconds=validated_data.get("uptime_seconds"),
            channel_utilization=validated_data.get("channel_utilization"),
            air_util_tx=validated_data.get("air_util_tx"),
            num_packets_tx=validated_data.get("num_packets_tx"),
            num_packets_rx=validated_data.get("num_packets_rx"),
            num_packets_rx_bad=validated_data.get("num_packets_rx_bad"),
            num_online_nodes=validated_data.get("num_online_nodes"),
            num_total_nodes=validated_data.get("num_total_nodes"),
            num_rx_dupe=validated_data.get("num_rx_dupe"),
            reading_time=validated_data.get("reading_time"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class PacketIngestSerializer(serializers.Serializer):
    """Serializer for ingesting packets of any type."""

    def to_internal_value(self, data):
        """Convert the incoming packet data to the appropriate packet type."""
        # Determine the packet type based on the portnum
        portnum = data.get("decoded", {}).get("portnum")

        if portnum == "TEXT_MESSAGE_APP":
            validated_data = MessagePacketSerializer().to_internal_value(data)
        elif portnum == "NODEINFO_APP":
            validated_data = NodeInfoPacketSerializer().to_internal_value(data)
        elif portnum == "POSITION_APP":
            validated_data = PositionPacketSerializer().to_internal_value(data)
        elif portnum == "TELEMETRY_APP":
            # Check if it's device metrics or local stats
            if "deviceMetrics" in data.get("decoded", {}).get("telemetry", {}):
                validated_data = DeviceMetricsPacketSerializer().to_internal_value(data)
            elif "localStats" in data.get("decoded", {}).get("telemetry", {}):
                validated_data = LocalStatsPacketSerializer().to_internal_value(data)
            else:
                raise serializers.ValidationError(
                    {"decoded.telemetry": "Must contain either deviceMetrics or localStats"}
                )
        else:
            raise serializers.ValidationError({"decoded.portnum": f"Unknown packet type: {portnum}"})

        return validated_data

    def create(self, validated_data):
        """Create the appropriate packet type based on the validated data."""
        # Determine the packet type based on the portnum
        portnum = validated_data.get("port_num")

        if portnum == "TEXT_MESSAGE_APP":
            packet = MessagePacketSerializer(context=self.context).create(validated_data)
        elif portnum == "NODEINFO_APP":
            packet = NodeInfoPacketSerializer(context=self.context).create(validated_data)
        elif portnum == "POSITION_APP":
            packet = PositionPacketSerializer(context=self.context).create(validated_data)
        elif portnum == "TELEMETRY_APP":
            # Check if it's device metrics or local stats
            if "battery_level" in validated_data:
                packet = DeviceMetricsPacketSerializer(context=self.context).create(validated_data)
            elif "num_packets_tx" in validated_data:
                packet = LocalStatsPacketSerializer(context=self.context).create(validated_data)
            else:
                raise serializers.ValidationError(
                    {"decoded.telemetry": "Must contain either deviceMetrics or localStats"}
                )
        else:
            raise serializers.ValidationError({"decoded.portnum": f"Unknown packet type: {portnum}"})

        return packet


class PositionSerializer(serializers.Serializer):
    logged_time = serializers.DateTimeField(read_only=True, default=django_timezone.now)
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
            validated_data["location_source"] = convert_location_source(validated_data["location_source"])

        return validated_data


class DeviceMetricsSerializer(serializers.Serializer):
    logged_time = serializers.DateTimeField(read_only=True, default=django_timezone.now)
    reported_time = serializers.DateTimeField(required=True)
    battery_level = serializers.FloatField()
    voltage = serializers.FloatField()
    channel_utilization = serializers.FloatField()
    air_util_tx = serializers.FloatField()
    uptime_seconds = serializers.IntegerField()


class NodeSerializer(serializers.ModelSerializer):
    """Serializer for node information updates."""

    class UserSerializer(serializers.Serializer):
        long_name = serializers.CharField(required=False, allow_null=True)
        short_name = serializers.CharField(required=False, allow_null=True)

    id = serializers.IntegerField(source="node_id")
    id_str = serializers.CharField(source="node_id_str")
    macaddr = serializers.CharField(source="mac_addr", allow_null=True, allow_blank=True)
    hw_model = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    public_key = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    user = UserSerializer(required=False)
    position = PositionSerializer(required=False, allow_null=True)
    device_metrics = DeviceMetricsSerializer(required=False, allow_null=True)

    class Meta:
        model = ObservedNode
        fields = [
            "id",
            "id_str",
            "macaddr",
            "hw_model",
            "public_key",
            "user",
            "position",
            "device_metrics",
            "long_name",
            "short_name",
            "last_heard",
        ]

    def to_internal_value(self, data):
        """Convert the incoming data to the appropriate format."""

        # Some clients _may_ send the node_id as a string, so we need to convert it to an integer
        if "id" in data:
            node_id = data["id"]
            # Add a warning if it's a hex string
            if isinstance(node_id, str) and node_id.startswith("!"):
                warnings = self.context.get("warnings", [])
                warnings.append("node id should be provided as an integer, not a hex string")
                self.context["warnings"] = warnings
                data["id"] = meshtastic_hex_to_int(node_id)
            elif isinstance(node_id, str):
                try:
                    data["id"] = int(node_id)
                except ValueError:
                    raise serializers.ValidationError({"id": "Invalid node ID format"})
            else:
                data["id"] = node_id

            data["id_str"] = meshtastic_id_to_hex(data["id"])

        # Handle the nested user data
        if "user" in data:
            user_data = data.pop("user")
            data.update(
                {
                    "long_name": user_data.get("long_name"),
                    "short_name": user_data.get("short_name"),
                }
            )

        # Handle position data
        if "position" in data:
            position_data = data.pop("position")
            data["position"] = {
                "reported_time": position_data.get("reported_time"),
                "latitude": position_data.get("latitude"),
                "longitude": position_data.get("longitude"),
                "altitude": position_data.get("altitude"),
                "location_source": position_data.get("location_source"),
            }

        # Handle device metrics
        if "device_metrics" in data:
            metrics_data = data.pop("device_metrics")
            data["device_metrics"] = {
                "reported_time": metrics_data.get("reported_time"),
                "battery_level": metrics_data.get("battery_level"),
                "voltage": metrics_data.get("voltage"),
                "channel_utilization": metrics_data.get("channel_utilization"),
                "air_util_tx": metrics_data.get("air_util_tx"),
                "uptime_seconds": metrics_data.get("uptime_seconds"),
            }

        return super().to_internal_value(data)

    def _create_related_objects(self, node, position_data, device_metrics_data):
        """Create position and device metrics records for a node."""
        # Create position if provided
        if position_data:
            Position.objects.create(
                node=node,
                reported_time=position_data.get("reported_time"),
                latitude=position_data.get("latitude"),
                longitude=position_data.get("longitude"),
                altitude=position_data.get("altitude"),
                location_source=position_data.get("location_source"),
            )

        # Create device metrics if provided
        if device_metrics_data:
            DeviceMetrics.objects.create(
                node=node,
                reported_time=device_metrics_data.get("reported_time"),
                battery_level=device_metrics_data.get("battery_level"),
                voltage=device_metrics_data.get("voltage"),
                channel_utilization=device_metrics_data.get("channel_utilization"),
                air_util_tx=device_metrics_data.get("air_util_tx"),
                uptime_seconds=device_metrics_data.get("uptime_seconds"),
            )

    def create(self, validated_data):
        """Create a new node instance."""
        # Handle position and device metrics data
        position_data = validated_data.pop("position", None)
        device_metrics_data = validated_data.pop("device_metrics", None)

        # Create the node
        node = ObservedNode.objects.create(**validated_data)

        # Create related objects
        self._create_related_objects(node, position_data, device_metrics_data)

        return node

    def update(self, instance, validated_data):
        """Update an existing node instance."""
        # Handle position and device metrics data
        position_data = validated_data.pop("position", None)
        device_metrics_data = validated_data.pop("device_metrics", None)

        # Update the node
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Create related objects
        self._create_related_objects(instance, position_data, device_metrics_data)

        return instance
