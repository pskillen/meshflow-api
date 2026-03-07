"""Serializers for the packets app."""

from datetime import datetime, timezone

from django.utils import timezone as django_timezone

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_hex_to_int, meshtastic_id_to_hex
from constellations.models import MessageChannel
from nodes.models import DeviceMetrics, ManagedNode, NodeLatestStatus, ObservedNode, Position

from .models import (
    AirQualityMetricsPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    LocalStatsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    PowerMetricsPacket,
    RoleSource,
    TrafficManagementStatsPacket,
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
    except ValueError, TypeError:
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

    # non-serialized fields
    observation: PacketObservation

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
        self.observation = None

        # Get the observer from the request context
        observer = self.context.get("observer")
        if not observer:
            raise serializers.ValidationError("No observer found in request context")

        # Check if this observer has already reported this packet
        existing_observation = PacketObservation.objects.filter(packet=packet, observer=observer).first()

        if existing_observation:
            # If the same observer reports the same packet again, ignore it
            self.observation = existing_observation
            return existing_observation

        # --- Channel FK resolution logic ---
        channel_value = validated_data.get("channel", 0)  # The bot often omits nullish fields
        channel_instance = None
        if channel_value is not None:

            if isinstance(channel_value, MessageChannel):
                channel_instance = channel_value
            else:
                # Channel is the index of the observer's channel_x field
                try:
                    # Get the observer's channel_x field
                    channel_field = f"channel_{channel_value}"
                    channel_instance = getattr(observer, channel_field)
                except AttributeError:
                    raise serializers.ValidationError(
                        {"channel": f"MessageChannel with id {channel_value} does not exist"}
                    )

        # Create new observation
        self.observation = PacketObservation.objects.create(
            packet=packet,
            observer=observer,
            channel=channel_instance,
            hop_limit=validated_data.get("hop_limit"),
            hop_start=validated_data.get("hop_start"),
            rx_time=validated_data.get("rx_time"),
            rx_rssi=validated_data.get("rx_rssi"),
            rx_snr=validated_data.get("rx_snr"),
            relay_node=validated_data.get("relay_node"),
        )

        return self.observation


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
        # Check if packet already exists
        packet_id = validated_data.get("packet_id")
        existing_packet = MessagePacket.objects.filter(packet_id=packet_id).first()

        if existing_packet:
            # If packet exists, just create the observation
            self._create_observation(existing_packet, validated_data)
            return existing_packet

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
        # Check if packet already exists
        packet_id = validated_data.get("packet_id")
        existing_packet = PositionPacket.objects.filter(packet_id=packet_id).first()

        if existing_packet:
            # If packet exists, just create the observation
            self._create_observation(existing_packet, validated_data)
            return existing_packet

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

        # Convert role from string or integer to RoleSource value (matches Meshtastic config.proto)
        if "role" in validated_data and validated_data["role"] is not None:
            try:
                role_val = validated_data["role"]
                if isinstance(role_val, int):
                    # Meshtastic may send protobuf enum value directly; use if valid
                    if role_val in [c.value for c in RoleSource]:
                        validated_data["role"] = role_val
                    else:
                        validated_data["role"] = None
                else:
                    # String: match by label (e.g. "CLIENT", "ROUTER")
                    role_str = str(role_val).strip()
                    for role_choice in RoleSource:
                        if role_choice.label == role_str:
                            validated_data["role"] = role_choice.value
                            break
                    else:
                        validated_data["role"] = None
            except ValueError, TypeError:
                validated_data["role"] = None

        return validated_data

    def create(self, validated_data):
        """Create a new NodeInfoPacket instance."""
        # Check if packet already exists
        packet_id = validated_data.get("packet_id")
        existing_packet = NodeInfoPacket.objects.filter(packet_id=packet_id).first()

        if existing_packet:
            # If packet exists, just create the observation
            self._create_observation(existing_packet, validated_data)
            return existing_packet

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
        # Check if packet already exists
        packet_id = validated_data.get("packet_id")
        existing_packet = DeviceMetricsPacket.objects.filter(packet_id=packet_id).first()

        if existing_packet:
            # If packet exists, just create the observation
            self._create_observation(existing_packet, validated_data)
            return existing_packet

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
                numTxRelay = serializers.IntegerField(source="num_tx_relay", required=False, allow_null=True)
                numTxRelayCanceled = serializers.IntegerField(
                    source="num_tx_relay_canceled", required=False, allow_null=True
                )
                heapTotalBytes = serializers.IntegerField(source="heap_total_bytes", required=False, allow_null=True)
                heapFreeBytes = serializers.IntegerField(source="heap_free_bytes", required=False, allow_null=True)
                numTxDropped = serializers.IntegerField(source="num_tx_dropped", required=False, allow_null=True)
                noiseFloor = serializers.IntegerField(source="noise_floor", required=False, allow_null=True)

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
        # Check if packet already exists
        packet_id = validated_data.get("packet_id")
        existing_packet = LocalStatsPacket.objects.filter(packet_id=packet_id).first()

        if existing_packet:
            # If packet exists, just create the observation
            self._create_observation(existing_packet, validated_data)
            return existing_packet

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
            num_tx_relay=validated_data.get("num_tx_relay"),
            num_tx_relay_canceled=validated_data.get("num_tx_relay_canceled"),
            heap_total_bytes=validated_data.get("heap_total_bytes"),
            heap_free_bytes=validated_data.get("heap_free_bytes"),
            num_tx_dropped=validated_data.get("num_tx_dropped"),
            noise_floor=validated_data.get("noise_floor"),
            reading_time=validated_data.get("reading_time"),
        )

        # Create the observation
        self._create_observation(packet, validated_data)

        return packet


class EnvironmentMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for environment metrics telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class EnvironmentMetricsSerializer(serializers.Serializer):
                temperature = serializers.FloatField(required=False, allow_null=True)
                relativeHumidity = serializers.FloatField(source="relative_humidity", required=False, allow_null=True)
                barometricPressure = serializers.FloatField(
                    source="barometric_pressure", required=False, allow_null=True
                )
                gasResistance = serializers.FloatField(source="gas_resistance", required=False, allow_null=True)
                voltage = serializers.FloatField(required=False, allow_null=True)
                current = serializers.FloatField(required=False, allow_null=True)
                iaq = serializers.IntegerField(required=False, allow_null=True)
                distance = serializers.FloatField(required=False, allow_null=True)
                lux = serializers.FloatField(required=False, allow_null=True)
                whiteLux = serializers.FloatField(source="white_lux", required=False, allow_null=True)
                irLux = serializers.FloatField(source="ir_lux", required=False, allow_null=True)
                uvLux = serializers.FloatField(source="uv_lux", required=False, allow_null=True)
                windDirection = serializers.IntegerField(source="wind_direction", required=False, allow_null=True)
                windSpeed = serializers.FloatField(source="wind_speed", required=False, allow_null=True)
                weight = serializers.FloatField(required=False, allow_null=True)
                windGust = serializers.FloatField(source="wind_gust", required=False, allow_null=True)
                windLull = serializers.FloatField(source="wind_lull", required=False, allow_null=True)
                radiation = serializers.FloatField(required=False, allow_null=True)
                rainfall1h = serializers.FloatField(source="rainfall_1h", required=False, allow_null=True)
                rainfall24h = serializers.FloatField(source="rainfall_24h", required=False, allow_null=True)
                soilMoisture = serializers.IntegerField(source="soil_moisture", required=False, allow_null=True)
                soilTemperature = serializers.FloatField(source="soil_temperature", required=False, allow_null=True)

            environmentMetrics = EnvironmentMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "environmentMetrics" in telemetry_data:
                env_data = telemetry_data.pop("environmentMetrics")
                validated_data.update(env_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = EnvironmentMetricsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = EnvironmentMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            temperature=validated_data.get("temperature"),
            relative_humidity=validated_data.get("relative_humidity"),
            barometric_pressure=validated_data.get("barometric_pressure"),
            gas_resistance=validated_data.get("gas_resistance"),
            iaq=validated_data.get("iaq"),
            voltage=validated_data.get("voltage"),
            current=validated_data.get("current"),
            distance=validated_data.get("distance"),
            lux=validated_data.get("lux"),
            white_lux=validated_data.get("white_lux"),
            ir_lux=validated_data.get("ir_lux"),
            uv_lux=validated_data.get("uv_lux"),
            wind_direction=validated_data.get("wind_direction"),
            wind_speed=validated_data.get("wind_speed"),
            weight=validated_data.get("weight"),
            wind_gust=validated_data.get("wind_gust"),
            wind_lull=validated_data.get("wind_lull"),
            radiation=validated_data.get("radiation"),
            rainfall_1h=validated_data.get("rainfall_1h"),
            rainfall_24h=validated_data.get("rainfall_24h"),
            soil_moisture=validated_data.get("soil_moisture"),
            soil_temperature=validated_data.get("soil_temperature"),
        )
        self._create_observation(packet, validated_data)
        return packet


class AirQualityMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for air quality metrics telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class AirQualityMetricsSerializer(serializers.Serializer):
                pm10Standard = serializers.IntegerField(source="pm10_standard", required=False, allow_null=True)
                pm25Standard = serializers.IntegerField(source="pm25_standard", required=False, allow_null=True)
                pm100Standard = serializers.IntegerField(source="pm100_standard", required=False, allow_null=True)
                pm10Environmental = serializers.IntegerField(
                    source="pm10_environmental", required=False, allow_null=True
                )
                pm25Environmental = serializers.IntegerField(
                    source="pm25_environmental", required=False, allow_null=True
                )
                pm100Environmental = serializers.IntegerField(
                    source="pm100_environmental", required=False, allow_null=True
                )
                particles03um = serializers.IntegerField(source="particles_03um", required=False, allow_null=True)
                particles05um = serializers.IntegerField(source="particles_05um", required=False, allow_null=True)
                particles10um = serializers.IntegerField(source="particles_10um", required=False, allow_null=True)
                particles25um = serializers.IntegerField(source="particles_25um", required=False, allow_null=True)
                particles50um = serializers.IntegerField(source="particles_50um", required=False, allow_null=True)
                particles100um = serializers.IntegerField(source="particles_100um", required=False, allow_null=True)
                co2 = serializers.IntegerField(required=False, allow_null=True)
                co2Temperature = serializers.FloatField(source="co2_temperature", required=False, allow_null=True)
                co2Humidity = serializers.FloatField(source="co2_humidity", required=False, allow_null=True)
                formFormaldehyde = serializers.FloatField(source="form_formaldehyde", required=False, allow_null=True)
                formHumidity = serializers.FloatField(source="form_humidity", required=False, allow_null=True)
                formTemperature = serializers.FloatField(source="form_temperature", required=False, allow_null=True)
                pm40Standard = serializers.IntegerField(source="pm40_standard", required=False, allow_null=True)
                particles40um = serializers.IntegerField(source="particles_40um", required=False, allow_null=True)
                pmTemperature = serializers.FloatField(source="pm_temperature", required=False, allow_null=True)
                pmHumidity = serializers.FloatField(source="pm_humidity", required=False, allow_null=True)
                pmVocIdx = serializers.FloatField(source="pm_voc_idx", required=False, allow_null=True)
                pmNoxIdx = serializers.FloatField(source="pm_nox_idx", required=False, allow_null=True)
                particlesTps = serializers.FloatField(source="particles_tps", required=False, allow_null=True)

            airQualityMetrics = AirQualityMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "airQualityMetrics" in telemetry_data:
                aq_data = telemetry_data.pop("airQualityMetrics")
                validated_data.update(aq_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = AirQualityMetricsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = AirQualityMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            pm10_standard=validated_data.get("pm10_standard"),
            pm25_standard=validated_data.get("pm25_standard"),
            pm100_standard=validated_data.get("pm100_standard"),
            pm10_environmental=validated_data.get("pm10_environmental"),
            pm25_environmental=validated_data.get("pm25_environmental"),
            pm100_environmental=validated_data.get("pm100_environmental"),
            particles_03um=validated_data.get("particles_03um"),
            particles_05um=validated_data.get("particles_05um"),
            particles_10um=validated_data.get("particles_10um"),
            particles_25um=validated_data.get("particles_25um"),
            particles_50um=validated_data.get("particles_50um"),
            particles_100um=validated_data.get("particles_100um"),
            co2=validated_data.get("co2"),
            co2_temperature=validated_data.get("co2_temperature"),
            co2_humidity=validated_data.get("co2_humidity"),
            form_formaldehyde=validated_data.get("form_formaldehyde"),
            form_humidity=validated_data.get("form_humidity"),
            form_temperature=validated_data.get("form_temperature"),
            pm40_standard=validated_data.get("pm40_standard"),
            particles_40um=validated_data.get("particles_40um"),
            pm_temperature=validated_data.get("pm_temperature"),
            pm_humidity=validated_data.get("pm_humidity"),
            pm_voc_idx=validated_data.get("pm_voc_idx"),
            pm_nox_idx=validated_data.get("pm_nox_idx"),
            particles_tps=validated_data.get("particles_tps"),
        )
        self._create_observation(packet, validated_data)
        return packet


class PowerMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for power metrics telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class PowerMetricsSerializer(serializers.Serializer):
                ch1Voltage = serializers.FloatField(source="ch1_voltage", required=False, allow_null=True)
                ch1Current = serializers.FloatField(source="ch1_current", required=False, allow_null=True)
                ch2Voltage = serializers.FloatField(source="ch2_voltage", required=False, allow_null=True)
                ch2Current = serializers.FloatField(source="ch2_current", required=False, allow_null=True)
                ch3Voltage = serializers.FloatField(source="ch3_voltage", required=False, allow_null=True)
                ch3Current = serializers.FloatField(source="ch3_current", required=False, allow_null=True)
                ch4Voltage = serializers.FloatField(source="ch4_voltage", required=False, allow_null=True)
                ch4Current = serializers.FloatField(source="ch4_current", required=False, allow_null=True)
                ch5Voltage = serializers.FloatField(source="ch5_voltage", required=False, allow_null=True)
                ch5Current = serializers.FloatField(source="ch5_current", required=False, allow_null=True)
                ch6Voltage = serializers.FloatField(source="ch6_voltage", required=False, allow_null=True)
                ch6Current = serializers.FloatField(source="ch6_current", required=False, allow_null=True)
                ch7Voltage = serializers.FloatField(source="ch7_voltage", required=False, allow_null=True)
                ch7Current = serializers.FloatField(source="ch7_current", required=False, allow_null=True)
                ch8Voltage = serializers.FloatField(source="ch8_voltage", required=False, allow_null=True)
                ch8Current = serializers.FloatField(source="ch8_current", required=False, allow_null=True)

            powerMetrics = PowerMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "powerMetrics" in telemetry_data:
                pm_data = telemetry_data.pop("powerMetrics")
                validated_data.update(pm_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = PowerMetricsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = PowerMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            ch1_voltage=validated_data.get("ch1_voltage"),
            ch1_current=validated_data.get("ch1_current"),
            ch2_voltage=validated_data.get("ch2_voltage"),
            ch2_current=validated_data.get("ch2_current"),
            ch3_voltage=validated_data.get("ch3_voltage"),
            ch3_current=validated_data.get("ch3_current"),
            ch4_voltage=validated_data.get("ch4_voltage"),
            ch4_current=validated_data.get("ch4_current"),
            ch5_voltage=validated_data.get("ch5_voltage"),
            ch5_current=validated_data.get("ch5_current"),
            ch6_voltage=validated_data.get("ch6_voltage"),
            ch6_current=validated_data.get("ch6_current"),
            ch7_voltage=validated_data.get("ch7_voltage"),
            ch7_current=validated_data.get("ch7_current"),
            ch8_voltage=validated_data.get("ch8_voltage"),
            ch8_current=validated_data.get("ch8_current"),
        )
        self._create_observation(packet, validated_data)
        return packet


class HealthMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for health metrics telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class HealthMetricsSerializer(serializers.Serializer):
                heartBpm = serializers.IntegerField(source="heart_bpm", required=False, allow_null=True)
                spO2 = serializers.IntegerField(source="spo2", required=False, allow_null=True)
                temperature = serializers.FloatField(required=False, allow_null=True)

            healthMetrics = HealthMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "healthMetrics" in telemetry_data:
                hm_data = telemetry_data.pop("healthMetrics")
                validated_data.update(hm_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = HealthMetricsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = HealthMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            heart_bpm=validated_data.get("heart_bpm"),
            spo2=validated_data.get("spo2"),
            temperature=validated_data.get("temperature"),
        )
        self._create_observation(packet, validated_data)
        return packet


class HostMetricsPacketSerializer(BasePacketSerializer):
    """Serializer for host metrics telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class HostMetricsSerializer(serializers.Serializer):
                uptimeSeconds = serializers.IntegerField(source="uptime_seconds", required=False, allow_null=True)
                freememBytes = serializers.IntegerField(source="freemem_bytes", required=False, allow_null=True)
                diskfree1Bytes = serializers.IntegerField(source="diskfree1_bytes", required=False, allow_null=True)
                diskfree2Bytes = serializers.IntegerField(source="diskfree2_bytes", required=False, allow_null=True)
                diskfree3Bytes = serializers.IntegerField(source="diskfree3_bytes", required=False, allow_null=True)
                load1 = serializers.IntegerField(required=False, allow_null=True)
                load5 = serializers.IntegerField(required=False, allow_null=True)
                load15 = serializers.IntegerField(required=False, allow_null=True)
                userString = serializers.CharField(source="user_string", required=False, allow_null=True)

            hostMetrics = HostMetricsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "hostMetrics" in telemetry_data:
                host_data = telemetry_data.pop("hostMetrics")
                validated_data.update(host_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = HostMetricsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = HostMetricsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            uptime_seconds=validated_data.get("uptime_seconds"),
            freemem_bytes=validated_data.get("freemem_bytes"),
            diskfree1_bytes=validated_data.get("diskfree1_bytes"),
            diskfree2_bytes=validated_data.get("diskfree2_bytes"),
            diskfree3_bytes=validated_data.get("diskfree3_bytes"),
            load1=validated_data.get("load1"),
            load5=validated_data.get("load5"),
            load15=validated_data.get("load15"),
            user_string=validated_data.get("user_string"),
        )
        self._create_observation(packet, validated_data)
        return packet


class TrafficManagementStatsPacketSerializer(BasePacketSerializer):
    """Serializer for traffic management stats telemetry packets."""

    class DecodedSerializer(serializers.Serializer):
        class TelemetrySerializer(serializers.Serializer):
            class TrafficManagementStatsSerializer(serializers.Serializer):
                packetsInspected = serializers.IntegerField(source="packets_inspected", required=False, allow_null=True)
                positionDedupDrops = serializers.IntegerField(
                    source="position_dedup_drops", required=False, allow_null=True
                )
                nodeinfoCacheHits = serializers.IntegerField(
                    source="nodeinfo_cache_hits", required=False, allow_null=True
                )
                rateLimitDrops = serializers.IntegerField(source="rate_limit_drops", required=False, allow_null=True)
                unknownPacketDrops = serializers.IntegerField(
                    source="unknown_packet_drops", required=False, allow_null=True
                )
                hopExhaustedPackets = serializers.IntegerField(
                    source="hop_exhausted_packets", required=False, allow_null=True
                )
                routerHopsPreserved = serializers.IntegerField(
                    source="router_hops_preserved", required=False, allow_null=True
                )

            trafficManagementStats = TrafficManagementStatsSerializer()
            time = serializers.IntegerField(source="reading_time")

        telemetry = TelemetrySerializer()

    decoded = DecodedSerializer(source="*")

    def to_internal_value(self, data):
        validated_data = super().to_internal_value(data)
        if "telemetry" in validated_data:
            telemetry_data = validated_data.pop("telemetry")
            if "trafficManagementStats" in telemetry_data:
                tm_data = telemetry_data.pop("trafficManagementStats")
                validated_data.update(tm_data)
            if "time" in telemetry_data:
                validated_data["reading_time"] = telemetry_data["time"]
            validated_data.update(telemetry_data)
        if "reading_time" in validated_data and validated_data["reading_time"] is not None:
            validated_data["reading_time"] = convert_timestamp(validated_data["reading_time"])
        return validated_data

    def create(self, validated_data):
        packet_id = validated_data.get("packet_id")
        existing_packet = TrafficManagementStatsPacket.objects.filter(packet_id=packet_id).first()
        if existing_packet:
            self._create_observation(existing_packet, validated_data)
            return existing_packet

        packet = TrafficManagementStatsPacket.objects.create(
            packet_id=validated_data.get("packet_id"),
            from_int=validated_data.get("from_int"),
            from_str=validated_data.get("from_str"),
            to_int=validated_data.get("to_int"),
            to_str=validated_data.get("to_str"),
            port_num=validated_data.get("port_num"),
            reading_time=validated_data.get("reading_time"),
            packets_inspected=validated_data.get("packets_inspected"),
            position_dedup_drops=validated_data.get("position_dedup_drops"),
            nodeinfo_cache_hits=validated_data.get("nodeinfo_cache_hits"),
            rate_limit_drops=validated_data.get("rate_limit_drops"),
            unknown_packet_drops=validated_data.get("unknown_packet_drops"),
            hop_exhausted_packets=validated_data.get("hop_exhausted_packets"),
            router_hops_preserved=validated_data.get("router_hops_preserved"),
        )
        self._create_observation(packet, validated_data)
        return packet


class PacketIngestSerializer(serializers.Serializer):
    """Serializer for ingesting packets of any type."""

    # non-serialized fields
    observation: PacketObservation
    child_serializer: BasePacketSerializer

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
            telemetry = data.get("decoded", {}).get("telemetry", {})
            if "deviceMetrics" in telemetry:
                validated_data = DeviceMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "deviceMetrics"
            elif "localStats" in telemetry:
                validated_data = LocalStatsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "localStats"
            elif "environmentMetrics" in telemetry:
                validated_data = EnvironmentMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "environmentMetrics"
            elif "airQualityMetrics" in telemetry:
                validated_data = AirQualityMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "airQualityMetrics"
            elif "powerMetrics" in telemetry:
                validated_data = PowerMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "powerMetrics"
            elif "healthMetrics" in telemetry:
                validated_data = HealthMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "healthMetrics"
            elif "hostMetrics" in telemetry:
                validated_data = HostMetricsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "hostMetrics"
            elif "trafficManagementStats" in telemetry:
                validated_data = TrafficManagementStatsPacketSerializer().to_internal_value(data)
                validated_data["_telemetry_variant"] = "trafficManagementStats"
            else:
                raise serializers.ValidationError(
                    {
                        "decoded.telemetry": "Must contain one of: deviceMetrics, localStats, "
                        "environmentMetrics, airQualityMetrics, powerMetrics, healthMetrics, "
                        "hostMetrics, trafficManagementStats"
                    }
                )
        else:
            raise serializers.ValidationError({"decoded.portnum": f"Unknown packet type: {portnum}"})

        return validated_data

    def create(self, validated_data):
        """Create the appropriate packet type based on the validated data."""
        # Determine the packet type based on the portnum
        portnum = validated_data.get("port_num")

        if portnum == "TEXT_MESSAGE_APP":
            self.child_serializer = MessagePacketSerializer(context=self.context)
        elif portnum == "NODEINFO_APP":
            self.child_serializer = NodeInfoPacketSerializer(context=self.context)
        elif portnum == "POSITION_APP":
            self.child_serializer = PositionPacketSerializer(context=self.context)
        elif portnum == "TELEMETRY_APP":
            variant = validated_data.pop("_telemetry_variant", None)
            variant_to_serializer = {
                "deviceMetrics": DeviceMetricsPacketSerializer,
                "localStats": LocalStatsPacketSerializer,
                "environmentMetrics": EnvironmentMetricsPacketSerializer,
                "airQualityMetrics": AirQualityMetricsPacketSerializer,
                "powerMetrics": PowerMetricsPacketSerializer,
                "healthMetrics": HealthMetricsPacketSerializer,
                "hostMetrics": HostMetricsPacketSerializer,
                "trafficManagementStats": TrafficManagementStatsPacketSerializer,
            }
            if variant and variant in variant_to_serializer:
                self.child_serializer = variant_to_serializer[variant](context=self.context)
            elif "battery_level" in validated_data:
                self.child_serializer = DeviceMetricsPacketSerializer(context=self.context)
            elif "num_packets_tx" in validated_data:
                self.child_serializer = LocalStatsPacketSerializer(context=self.context)
            else:
                raise serializers.ValidationError(
                    {
                        "decoded.telemetry": "Must contain one of: deviceMetrics, localStats, "
                        "environmentMetrics, airQualityMetrics, powerMetrics, healthMetrics, "
                        "hostMetrics, trafficManagementStats"
                    }
                )
        else:
            raise serializers.ValidationError({"decoded.portnum": f"Unknown packet type: {portnum}"})

        packet = self.child_serializer.create(validated_data)
        self.observation = self.child_serializer.observation
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
            reported_time = position_data.get("reported_time")
            Position.objects.create(
                node=node,
                reported_time=reported_time,
                latitude=position_data.get("latitude"),
                longitude=position_data.get("longitude"),
                altitude=position_data.get("altitude"),
                location_source=position_data.get("location_source"),
            )
            # Update NodeLatestStatus with latest position
            NodeLatestStatus.objects.update_or_create(
                node=node,
                defaults={
                    "latitude": position_data.get("latitude"),
                    "longitude": position_data.get("longitude"),
                    "altitude": position_data.get("altitude"),
                    "location_source": position_data.get("location_source"),
                    "position_reported_time": reported_time,
                },
            )

        # Create device metrics if provided
        if device_metrics_data:
            reported_time = device_metrics_data.get("reported_time")
            DeviceMetrics.objects.create(
                node=node,
                reported_time=reported_time,
                battery_level=device_metrics_data.get("battery_level"),
                voltage=device_metrics_data.get("voltage"),
                channel_utilization=device_metrics_data.get("channel_utilization"),
                air_util_tx=device_metrics_data.get("air_util_tx"),
                uptime_seconds=device_metrics_data.get("uptime_seconds"),
            )
            # Update NodeLatestStatus with latest device metrics
            NodeLatestStatus.objects.update_or_create(
                node=node,
                defaults={
                    "battery_level": device_metrics_data.get("battery_level"),
                    "voltage": device_metrics_data.get("voltage"),
                    "channel_utilization": device_metrics_data.get("channel_utilization"),
                    "air_util_tx": device_metrics_data.get("air_util_tx"),
                    "uptime_seconds": device_metrics_data.get("uptime_seconds"),
                    "metrics_reported_time": reported_time,
                },
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


class PrefetchedPacketObservationSerializer(serializers.ModelSerializer):
    """Serializer for packet observations."""

    class ObserverSerializer(serializers.ModelSerializer):
        """Serializer for the observer node."""

        long_name = serializers.SerializerMethodField()
        short_name = serializers.SerializerMethodField()

        class Meta:
            model = ManagedNode
            fields = ["node_id", "node_id_str", "long_name", "short_name"]

        def __init__(self, *args, **kwargs):
            # Always pass parent context to this serializer
            parent = kwargs.pop("parent", None)
            if parent is not None:
                kwargs["context"] = parent.context
            super().__init__(*args, **kwargs)

        def get_long_name(self, obj):
            """
            Return the long_name from the corresponding ObservedNode if it exists,
            otherwise return the ManagedNode's name.
            """
            # Try to get ObservedNode from prefetch cache
            observed_node = self._get_observed_node(obj)
            if observed_node:
                return observed_node.long_name
            return obj.name

        def get_short_name(self, obj):
            """
            Return the short_name from the corresponding ObservedNode if it exists,
            otherwise return the ManagedNode's node_id_str.
            """
            observed_node = self._get_observed_node(obj)
            if observed_node:
                return observed_node.short_name
            return obj.node_id_str

        def _get_observed_node(self, obj):
            # Use pre-fetched observed nodes if available
            # The parent serializer context should have a mapping: node_id -> ObservedNode
            observer_nodes_map = self.context.get("observer_nodes_map")
            if observer_nodes_map:
                return observer_nodes_map.get(obj.node_id)
            # Fallback: try to use prefetch cache (if using prefetch_related)
            if hasattr(obj, "prefetched_observed_nodes") and obj.prefetched_observed_nodes:
                return obj.prefetched_observed_nodes[0]
            # Fallback: DB hit (should be rare)
            return ObservedNode.objects.filter(node_id=obj.node_id).first()

    # observer = serializers.SerializerMethodField()
    observer = ObserverSerializer(read_only=True)
    direct_from_sender = serializers.SerializerMethodField()
    hop_count = serializers.SerializerMethodField()

    class Meta:
        model = PacketObservation
        fields = [
            "observer",
            "rx_time",
            "rx_rssi",
            "rx_snr",
            "direct_from_sender",
            "hop_count",
        ]

    def get_direct_from_sender(self, obj):
        """Return True if the packet was heard directly from the sender."""
        return obj.hop_start == obj.hop_limit

    def get_hop_count(self, obj):
        """Return the hop count (hop_start minus hop_limit)."""
        if obj.hop_start is None or obj.hop_limit is None:
            return None
        return obj.hop_start - obj.hop_limit

    def get_observer(self, obj):
        # Pass self as parent so context is inherited
        return self.ObserverSerializer(obj.observer, parent=self).data
