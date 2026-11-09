"""Tests for packet serializers."""

from datetime import datetime, timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from constellations.models import Constellation, MessageChannel
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode, Position
from packets.models import (
    DeviceMetricsPacket,
    GenericPacket,
    LocalStatsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PositionPacket,
    RoleSource,
    TraceroutePacket,
)
from packets.serializers import (
    BasePacketSerializer,
    DeviceMetricsPacketSerializer,
    LocalStatsPacketSerializer,
    MessagePacketSerializer,
    NodeInfoPacketSerializer,
    NodeSerializer,
    PacketIngestSerializer,
    PositionPacketSerializer,
)

User = get_user_model()


def assert_serializer_valid(serializer):
    """Assert that a serializer is valid."""
    valid = serializer.is_valid()
    if not valid:
        print(serializer.errors)
    assert valid


class BasePacketSerializerTestCase(TestCase):
    """Base test case for packet serializers."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test cases."""
        # Create a test user
        cls.user = User.objects.create_user(username="testuser", password="testpass123", email="test@example.com")

        # Create a test constellation
        cls.constellation = Constellation.objects.create(name="Test Constellation", created_by=cls.user)

        # Create a test observer node
        cls.observer = ManagedNode.objects.create(
            internal_id=uuid4(),
            meshtastic_node_id=123456789,
            name="Test Node",
            constellation_id=cls.constellation.id,
            owner=cls.user,
        )

        cls.from_node = ObservedNode.objects.create(
            meshtastic_node_id=456789,
            long_name="From Node",
            short_name="FRM",
        )

    def setUp(self):
        """Set up test context."""
        self.context = {"observer": self.observer}


class BasePacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for BasePacketSerializer."""

    def test_base_packet_serialization(self):
        """Test basic packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "to": 789,
            "toId": "!789012",
            "decoded": {"portnum": "TEXT_MESSAGE_APP"},
            "rxTime": 1672531200,  # 2023-01-01 00:00:00 UTC
            "hopLimit": 5,
            "hopStart": 10,
            "rxRssi": -65.5,
            "rxSnr": 12.3,
            "relayNode": 101112,
            "pkiEncrypted": True,
            "nextHop": 131415,
            "priority": "RELIABLE",
            "raw": "raw data",
        }

        serializer = BasePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test field mapping
        self.assertEqual(validated_data["packet_id"], 123)
        self.assertEqual(validated_data["from_int"], self.from_node.meshtastic_node_id)
        self.assertEqual(validated_data["from_str"], self.from_node.node_id_str)
        self.assertEqual(validated_data["to_int"], 789)
        self.assertEqual(validated_data["to_str"], "!789012")
        self.assertEqual(validated_data["port_num"], "TEXT_MESSAGE_APP")

        # Test timestamp conversion
        expected_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(validated_data["rx_time"], expected_time)

        # Test optional fields
        self.assertEqual(validated_data["hop_limit"], 5)
        self.assertEqual(validated_data["hop_start"], 10)
        self.assertEqual(validated_data["rx_rssi"], -65.5)
        self.assertEqual(validated_data["rx_snr"], 12.3)
        self.assertEqual(validated_data["relay_node"], 101112)
        self.assertEqual(validated_data["pki_encrypted"], True)
        self.assertEqual(validated_data["next_hop"], 131415)
        self.assertEqual(validated_data["priority"], "RELIABLE")
        self.assertEqual(validated_data["raw"], "raw data")

    def _base_data(self, **extra):
        data = {"id": 123, "from": 0x1A83CF89, "decoded": {"portnum": "TEXT_MESSAGE_APP"}, "rxTime": 1672531200}
        data.update(extra)
        return data

    def test_from_str_derived_when_from_id_null(self):
        """The bot sends fromId null when the sender is not in the feeder's NodeDB; derive the hex from `from`."""
        serializer = BasePacketSerializer(data=self._base_data(fromId=None), context=self.context)
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["from_str"], "!1a83cf89")

    def test_from_str_derived_when_from_id_absent(self):
        serializer = BasePacketSerializer(data=self._base_data(), context=self.context)
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["from_str"], "!1a83cf89")

    def test_to_str_derived_when_to_id_null(self):
        serializer = BasePacketSerializer(data=self._base_data(to=0x0A0B0C0D, toId=None), context=self.context)
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["to_str"], "!0a0b0c0d")

    def test_to_str_derived_for_broadcast(self):
        serializer = BasePacketSerializer(data=self._base_data(to=0xFFFFFFFF, toId=None), context=self.context)
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["to_str"], "^all")

    def test_to_str_not_invented_without_to(self):
        serializer = BasePacketSerializer(data=self._base_data(toId=None), context=self.context)
        assert_serializer_valid(serializer)
        self.assertIsNone(serializer.validated_data.get("to_str"))

    def test_supplied_ids_are_kept(self):
        """A supplied fromId/toId is stored as sent, as before."""
        serializer = BasePacketSerializer(
            data=self._base_data(fromId="!cafef00d", to=789, toId="!789012"), context=self.context
        )
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["from_str"], "!cafef00d")
        self.assertEqual(serializer.validated_data["to_str"], "!789012")

    def test_invalid_timestamp(self):
        """Test handling of invalid timestamps."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP"},
            "rxTime": "invalid",
        }

        serializer = BasePacketSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("rxTime", serializer.errors)


class MessagePacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for MessagePacketSerializer."""

    def test_message_packet_serialization(self):
        """Test message packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Hello, world!",
                "replyId": 789,
                "emoji": 1,
            },
            "rxTime": 1672531200,
        }

        serializer = MessagePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test message-specific fields
        self.assertEqual(validated_data["message_text"], "Hello, world!")
        self.assertEqual(validated_data["reply_packet_id"], 789)
        self.assertTrue(validated_data["emoji"])

    def test_create_message_packet(self):
        """Test creating a message packet."""
        data = {
            "id": 123456789,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Hello, world!",
            },
            "rxTime": 1672531200,
        }

        serializer = MessagePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, MessagePacket)
        self.assertEqual(packet.packet_id, 123456789)
        self.assertEqual(packet.message_text, "Hello, world!")

        # Verify observation creation
        self.assertEqual(packet.observations.count(), 1)
        observation = packet.observations.first()
        self.assertEqual(observation.observer, self.observer)

    def test_create_message_packet_with_channel(self):
        """Test creating a message packet with a channel index sets the correct FK on PacketObservation."""

        # Create a MessageChannel for the observer's constellation
        message_channel = MessageChannel.objects.create(
            name="Test Channel",
            constellation=self.observer.constellation,
        )
        # Assign to observer's meshtastic_channel_0
        self.observer.meshtastic_channel_0 = message_channel
        self.observer.save()

        data = {
            "id": 987654321,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Channel test!",
            },
            "rxTime": 1672531200,
            "channel": 0,  # Pass the channel index
        }

        serializer = MessagePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, MessagePacket)
        self.assertEqual(packet.packet_id, 987654321)
        self.assertEqual(packet.message_text, "Channel test!")

        # Verify observation creation and correct channel FK
        self.assertEqual(packet.observations.count(), 1)
        observation = packet.observations.first()
        self.assertEqual(observation.observer, self.observer)
        self.assertIsNotNone(observation.channel)
        self.assertEqual(observation.channel, message_channel)


class PositionPacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for PositionPacketSerializer."""

    def test_position_packet_serialization(self):
        """Test position packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "altitude": 10.5,
                    "heading": 90.0,
                    "locationSource": "LOC_INTERNAL",
                    "precisionBits": 32,
                    "time": 1672531200,
                    "groundSpeed": 5.5,
                    "groundTrack": 90.0,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = PositionPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test position-specific fields
        self.assertEqual(validated_data["latitude"], 37.7749)
        self.assertEqual(validated_data["longitude"], -122.4194)
        self.assertEqual(validated_data["altitude"], 10.5)
        self.assertEqual(validated_data["heading"], 90.0)
        self.assertEqual(validated_data["meshtastic_location_source"], LocationSource.INTERNAL)
        self.assertEqual(validated_data["meshtastic_precision_bits"], 32)
        self.assertEqual(validated_data["ground_speed"], 5.5)
        self.assertEqual(validated_data["ground_track"], 90.0)

    def test_create_position_packet(self):
        """Test creating a position packet."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "altitude": 10.5,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = PositionPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, PositionPacket)
        self.assertEqual(packet.packet_id, 123)
        self.assertEqual(packet.latitude, 37.7749)
        self.assertEqual(packet.longitude, -122.4194)
        self.assertEqual(packet.altitude, 10.5)


class NodeInfoPacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for NodeInfoPacketSerializer."""

    def test_node_info_packet_serialization(self):
        """Test node info packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {
                    "id": "!789012",
                    "shortName": "TEST",
                    "longName": "Test Node",
                    "hwModel": "TBEAM",
                    "publicKey": "public_key",
                    "macaddr": "00:11:22:33:44:55",
                    "role": "ROUTER",
                    "isLicensed": True,
                    "isUnmessagable": False,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = NodeInfoPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test node info-specific fields
        self.assertEqual(validated_data["node_id"], "!789012")
        self.assertEqual(validated_data["short_name"], "TEST")
        self.assertEqual(validated_data["long_name"], "Test Node")
        self.assertEqual(validated_data["hw_model"], "TBEAM")
        self.assertEqual(validated_data["public_key"], "public_key")
        self.assertEqual(validated_data["mac_address"], "00:11:22:33:44:55")
        self.assertEqual(validated_data["role"], RoleSource.ROUTER)
        self.assertEqual(validated_data["is_licensed"], True)
        self.assertEqual(validated_data["is_unmessagable"], False)

    def test_node_info_packet_mac_base64_conversion(self):
        """Test that base64 MAC address from Meshtastic is converted to colon-separated hex."""
        # Meshtastic sends macaddr as base64 (protobuf bytes). AAECAwQFBg== decodes to 00:01:02:03:04:05:06
        data = {
            "id": 456,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {
                    "id": "!789012",
                    "shortName": "TEST",
                    "macaddr": "AAECAwQFBg==",
                },
            },
            "rxTime": 1672531200,
        }
        serializer = NodeInfoPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        self.assertEqual(serializer.validated_data["mac_address"], "00:01:02:03:04:05:06")

    def test_create_node_info_packet(self):
        """Test creating a node info packet."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {
                    "id": "!789012",
                    "shortName": "TEST",
                    "longName": "Test Node",
                },
            },
            "rxTime": 1672531200,
        }

        serializer = NodeInfoPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, NodeInfoPacket)
        self.assertEqual(packet.packet_id, 123)
        self.assertEqual(packet.node_id, "!789012")
        self.assertEqual(packet.short_name, "TEST")
        self.assertEqual(packet.long_name, "Test Node")


class DeviceMetricsPacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for DeviceMetricsPacketSerializer."""

    def test_device_metrics_packet_serialization(self):
        """Test device metrics packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "deviceMetrics": {
                        "batteryLevel": 95.5,
                        "voltage": 3.7,
                        "channelUtilization": 0.5,
                        "airUtilTx": 0.3,
                        "uptimeSeconds": 3600,
                    },
                    "time": 1672531200,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = DeviceMetricsPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test device metrics-specific fields
        self.assertEqual(validated_data["battery_level"], 95.5)
        self.assertEqual(validated_data["voltage"], 3.7)
        self.assertEqual(validated_data["meshtastic_channel_utilization"], 0.5)
        self.assertEqual(validated_data["meshtastic_air_util_tx"], 0.3)
        self.assertEqual(validated_data["uptime_seconds"], 3600)

    def test_create_device_metrics_packet(self):
        """Test creating a device metrics packet."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "deviceMetrics": {
                        "batteryLevel": 95.5,
                        "voltage": 3.7,
                    },
                    "time": 1672531200,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = DeviceMetricsPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, DeviceMetricsPacket)
        self.assertEqual(packet.packet_id, 123)
        self.assertEqual(packet.battery_level, 95.5)
        self.assertEqual(packet.voltage, 3.7)


class LocalStatsPacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for LocalStatsPacketSerializer."""

    def test_local_stats_packet_serialization(self):
        """Test local stats packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "localStats": {
                        "uptimeSeconds": 3600,
                        "channelUtilization": 0.5,
                        "airUtilTx": 0.3,
                        "numPacketsTx": 100,
                        "numPacketsRx": 200,
                        "numPacketsRxBad": 5,
                        "numOnlineNodes": 10,
                        "numTotalNodes": 15,
                        "numRxDupe": 2,
                    },
                    "time": 1672531200,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = LocalStatsPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        validated_data = serializer.validated_data

        # Test local stats-specific fields
        self.assertEqual(validated_data["uptime_seconds"], 3600)
        self.assertEqual(validated_data["meshtastic_channel_utilization"], 0.5)
        self.assertEqual(validated_data["meshtastic_air_util_tx"], 0.3)
        self.assertEqual(validated_data["num_packets_tx"], 100)
        self.assertEqual(validated_data["num_packets_rx"], 200)
        self.assertEqual(validated_data["num_packets_rx_bad"], 5)
        self.assertEqual(validated_data["num_online_nodes"], 10)
        self.assertEqual(validated_data["num_total_nodes"], 15)
        self.assertEqual(validated_data["num_rx_dupe"], 2)

    def test_create_local_stats_packet(self):
        """Test creating a local stats packet."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "localStats": {
                        "uptimeSeconds": 3600,
                        "channelUtilization": 0.5,
                    },
                    "time": 1672531200,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = LocalStatsPacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify model creation
        self.assertIsInstance(packet, LocalStatsPacket)
        self.assertEqual(packet.packet_id, 123)
        self.assertEqual(packet.uptime_seconds, 3600)
        self.assertEqual(packet.meshtastic_channel_utilization, 0.5)


class PacketIngestSerializerTest(BasePacketSerializerTestCase):
    """Tests for PacketIngestSerializer."""

    def test_message_packet_ingest(self):
        """Test ingesting a message packet."""
        data = {
            "id": 123456789,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Hello, world!",
            },
            "rxTime": 1672531200,
        }

        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify correct packet type was created
        self.assertIsInstance(packet, MessagePacket)
        self.assertEqual(packet.message_text, "Hello, world!")

    def test_position_packet_ingest(self):
        """Test ingesting a position packet."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                },
            },
            "rxTime": 1672531200,
        }

        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify correct packet type was created
        self.assertIsInstance(packet, PositionPacket)
        self.assertEqual(packet.latitude, 37.7749)
        self.assertEqual(packet.longitude, -122.4194)

    def test_traceroute_packet_ingest(self):
        """Test ingesting a TRACEROUTE_APP packet."""
        data = {
            "id": 987654321,
            "from": 1623194643,
            "fromId": "!60b0e093",
            "to": 123456789,
            "toId": "!499602d",
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": {
                    "route": [111111, 222222],
                    "routeBack": [222222, 111111],
                    "snrTowards": [18, -12],  # Scaled by 4: 4.5 dB, -3 dB
                    "snrBack": [8],
                },
            },
            "rxTime": 1745330928,
            "hopLimit": 6,
            "hopStart": 6,
        }

        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()

        # Verify correct packet type was created
        self.assertIsInstance(packet, TraceroutePacket)
        self.assertEqual(packet.route, [111111, 222222])
        self.assertEqual(packet.route_back, [222222, 111111])
        self.assertEqual(packet.snr_towards, [4.5, -3.0])
        self.assertEqual(packet.snr_back, [2.0])
        self.assertEqual(packet.from_int, 1623194643)

    def test_traceroute_packet_ingest_without_snr(self):
        """Test TRACEROUTE_APP without snrTowards/snrBack (older firmware)."""
        data = {
            "id": 987654322,
            "from": 1623194643,
            "fromId": "!60b0e093",
            "to": 123456789,
            "toId": "!499602d",
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": {
                    "route": [111111],
                    "routeBack": [111111],
                },
            },
            "rxTime": 1745330929,
            "hopLimit": 6,
            "hopStart": 6,
        }
        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()
        self.assertIsInstance(packet, TraceroutePacket)
        self.assertEqual(packet.snr_towards, [])
        self.assertEqual(packet.snr_back, [])

    def test_traceroute_packet_ingest_unknown_snr(self):
        """Test TRACEROUTE_APP with -128 (unknown SNR from older firmware)."""
        data = {
            "id": 987654323,
            "from": 1623194643,
            "fromId": "!60b0e093",
            "to": 123456789,
            "toId": "!499602d",
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": {
                    "route": [111111, 222222],
                    "routeBack": [222222],
                    "snrTowards": [18, -128],
                    "snrBack": [-128],
                },
            },
            "rxTime": 1745330930,
            "hopLimit": 6,
            "hopStart": 6,
        }
        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()
        self.assertEqual(packet.snr_towards, [4.5, None])
        self.assertEqual(packet.snr_back, [None])
        self.assertEqual(packet.to_int, 123456789)
        # Verify PacketObservation was created
        self.assertEqual(packet.observations.count(), 1)
        self.assertEqual(packet.observations.first().observer, self.observer)

    def test_traceroute_packet_ingest_snr_longer_than_route(self):
        """Test TRACEROUTE_APP with snrTowards one element longer than route (firmware edge case)."""
        data = {
            "id": 987654324,
            "from": 1623194643,
            "fromId": "!60b0e093",
            "to": 123456789,
            "toId": "!499602d",
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": {
                    "route": [111111, 222222],
                    "routeBack": [222222, 111111],
                    "snrTowards": [18, -12, 4],  # 3 values for 2 route nodes
                    "snrBack": [8, 0, -4],
                },
            },
            "rxTime": 1745330931,
            "hopLimit": 6,
            "hopStart": 6,
        }
        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()
        self.assertIsInstance(packet, TraceroutePacket)
        self.assertEqual(packet.route, [111111, 222222])
        self.assertEqual(packet.snr_towards, [4.5, -3.0, 1.0])  # Extra value stored, receiver uses i < len
        self.assertEqual(packet.snr_back, [2.0, 0.0, -1.0])

    def test_unknown_packet_type_is_generic(self):
        """An unknown port is stored as a GenericPacket, not rejected."""
        data = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "INVALID_TYPE"},
            "rxTime": 1672531200,
        }

        serializer = PacketIngestSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer)
        packet = serializer.save()
        self.assertIsInstance(packet, GenericPacket)
        self.assertEqual(packet.port_num, "INVALID_TYPE")

    def test_missing_portnum_is_invalid(self):
        """A packet with no decoded.portnum is still a 400."""
        data = {"id": 123, "from": self.from_node.meshtastic_node_id, "decoded": {}, "rxTime": 1672531200}

        serializer = PacketIngestSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("decoded.portnum", serializer.errors)


class NodeSerializerTest(BasePacketSerializerTestCase):
    """Tests for NodeSerializer."""

    def test_node_upsert_with_position_updates_nodelateststatus(self):
        """Test that creating a node with position updates NodeLatestStatus."""
        from django.utils import timezone

        data = {
            "id": self.from_node.meshtastic_node_id,
            "id_str": self.from_node.node_id_str,
            "long_name": "Updated Node",
            "short_name": "UPD",
            "position": {
                "reported_time": timezone.now().isoformat(),
                "latitude": 40.7128,
                "longitude": -74.0060,
                "altitude": 10.0,
                "heading": 0.0,
                "meshtastic_location_source": "UNSET",
            },
        }

        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.latitude, 40.7128)
        self.assertEqual(latest_status.longitude, -74.0060)
        self.assertEqual(latest_status.altitude, 10.0)
        self.assertIsNotNone(latest_status.position_reported_time)

    def test_node_upsert_with_device_metrics_updates_nodelateststatus(self):
        """Test that creating a node with device_metrics updates NodeLatestStatus."""
        from django.utils import timezone

        data = {
            "id": self.from_node.meshtastic_node_id,
            "id_str": self.from_node.node_id_str,
            "long_name": "Updated Node",
            "short_name": "UPD",
            "device_metrics": {
                "reported_time": timezone.now().isoformat(),
                "battery_level": 85.0,
                "voltage": 3.9,
                "meshtastic_channel_utilization": 0.2,
                "meshtastic_air_util_tx": 0.3,
                "uptime_seconds": 10000,
            },
        }

        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.battery_level, 85.0)
        self.assertEqual(latest_status.voltage, 3.9)
        self.assertEqual(latest_status.meshtastic_channel_utilization, 0.2)
        self.assertEqual(latest_status.meshtastic_air_util_tx, 0.3)
        self.assertEqual(latest_status.uptime_seconds, 10000)
        self.assertIsNotNone(latest_status.metrics_reported_time)

    def test_node_upsert_v2_compat_legacy_position_and_metrics_fields(self):
        """Legacy bot wire (location_source, channel_utilization) validates on v2 serializer."""
        from django.utils import timezone

        data = {
            "id": self.from_node.meshtastic_node_id,
            "position": {
                "reported_time": timezone.now().isoformat(),
                "latitude": 51.5,
                "longitude": -0.12,
                "altitude": 5.0,
                "location_source": "",
            },
            "device_metrics": {
                "reported_time": timezone.now().isoformat(),
                "battery_level": 90.0,
                "voltage": 4.0,
                "channel_utilization": 0.15,
                "air_util_tx": 0.05,
                "uptime_seconds": 5000,
            },
        }

        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.meshtastic_location_source, LocationSource.UNSET)
        self.assertEqual(latest_status.meshtastic_channel_utilization, 0.15)
        self.assertEqual(latest_status.meshtastic_air_util_tx, 0.05)

    def test_node_upsert_sets_predicted_node_id_from_public_key(self):
        data = {
            "id": self.from_node.meshtastic_node_id,
            "meshtastic_public_key": "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs=",
        }
        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        self.from_node.refresh_from_db()
        self.assertEqual(
            self.from_node.meshtastic_public_key_hex,
            "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b",
        )
        self.assertEqual(self.from_node.meshtastic_key_node_id, 0x4396524C)

    def test_node_upsert_malformed_public_key_gives_null_prediction(self):
        data = {"id": self.from_node.meshtastic_node_id, "meshtastic_public_key": "short"}
        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        self.from_node.refresh_from_db()
        self.assertIsNone(self.from_node.meshtastic_public_key_hex)
        self.assertIsNone(self.from_node.meshtastic_key_node_id)

    # --- 2.8 NodeDB upserts must not clobber identity data (ID-8) ---

    KEY = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
    KEY_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
    FULL_NAME = "Highland Ridge Repeater North-East"

    def _seed_identity(self):
        self.from_node.mac_addr = "a0:b3:a9:cf:5a:7b"
        self.from_node.long_name = self.FULL_NAME
        self.from_node.meshtastic_public_key = self.KEY
        self.from_node.meshtastic_public_key_hex = self.KEY_HEX
        self.from_node.meshtastic_key_node_id = 0x4396524C
        self.from_node.save()

    def _upsert(self, **extra):
        data = {"id": self.from_node.meshtastic_node_id, **extra}
        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()
        self.from_node.refresh_from_db()

    def test_node_upsert_28_nodedb_payload_keeps_mac_name_and_key(self):
        self._seed_identity()
        self._upsert(
            macaddr="00:00:00:00:00:00",
            meshtastic_public_key="",
            user={"long_name": self.FULL_NAME.encode()[:24].decode(), "short_name": "HRRN"},
        )
        self.assertEqual(self.from_node.mac_addr, "a0:b3:a9:cf:5a:7b")
        self.assertEqual(self.from_node.long_name, self.FULL_NAME)
        self.assertEqual(self.from_node.meshtastic_public_key, self.KEY)
        self.assertEqual(self.from_node.meshtastic_public_key_hex, self.KEY_HEX)
        self.assertEqual(self.from_node.meshtastic_key_node_id, 0x4396524C)
        self.assertEqual(self.from_node.short_name, "HRRN")

    def test_node_upsert_null_key_and_null_mac_keep_stored_values(self):
        self._seed_identity()
        self._upsert(macaddr=None, meshtastic_public_key=None)
        self.assertEqual(self.from_node.mac_addr, "a0:b3:a9:cf:5a:7b")
        self.assertEqual(self.from_node.meshtastic_public_key, self.KEY)
        self.assertEqual(self.from_node.meshtastic_key_node_id, 0x4396524C)

    def test_node_upsert_real_changes_still_apply(self):
        self._seed_identity()
        new_key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
        self._upsert(
            macaddr="11:22:33:44:55:66",
            meshtastic_public_key=new_key,
            user={"long_name": "Renamed Node", "short_name": "RENM"},
        )
        self.assertEqual(self.from_node.mac_addr, "11:22:33:44:55:66")
        self.assertEqual(self.from_node.long_name, "Renamed Node")
        self.assertEqual(self.from_node.meshtastic_public_key, new_key)
        self.assertEqual(
            self.from_node.meshtastic_public_key_hex,
            "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
        )

    def test_node_upsert_multibyte_truncated_name_keeps_stored_name(self):
        stored = "Café Ünïcödé NødeÅlesund Relay"
        self.from_node.long_name = stored
        self.from_node.save()
        self._upsert(user={"long_name": stored.encode()[:24].decode(errors="ignore"), "short_name": "CAFE"})
        self.assertEqual(self.from_node.long_name, stored)

    # --- G28: a NodeDB upload must not replace a name learned more recently from the air ---------------

    def _nodeinfo_at(self, when):
        from packets.models import NodeInfoPacket

        return NodeInfoPacket.objects.create(
            packet_id=1,
            from_int=self.from_node.meshtastic_node_id,
            first_reported_time=when,
            node_id=self.from_node.node_id_str,
            long_name="TIGERBAWS",
            short_name="TIGR",
        )

    def _seed_names(self, long_name="TIGERBAWS", short_name="TIGR"):
        self.from_node.long_name = long_name
        self.from_node.short_name = short_name
        self.from_node.save()

    def test_node_upsert_stale_last_heard_keeps_newer_onair_name(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        self._seed_names()
        self._nodeinfo_at(now)
        self._upsert(
            user={"long_name": "Old Name", "short_name": "OLD"},
            last_heard=(now - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(self.from_node.long_name, "TIGERBAWS")
        self.assertEqual(self.from_node.short_name, "TIGR")

    def test_node_upsert_newer_last_heard_still_keeps_onair_name(self):
        """NodeDB last_heard is the last packet of any type, so a newer one does not beat an on-air name."""
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        self._seed_names()
        self._nodeinfo_at(now - timedelta(days=2))
        self._upsert(
            user={"long_name": "Old Name", "short_name": "OLD"},
            last_heard=now.isoformat(),
        )
        self.assertEqual(self.from_node.long_name, "TIGERBAWS")
        self.assertEqual(self.from_node.short_name, "TIGR")

    def test_node_upsert_without_nodeinfo_applies_real_name(self):
        from django.utils import timezone

        self._seed_names()
        self._upsert(
            user={"long_name": "Fresh Name", "short_name": "NEW"},
            last_heard=timezone.now().isoformat(),
        )
        self.assertEqual(self.from_node.long_name, "Fresh Name")
        self.assertEqual(self.from_node.short_name, "NEW")

    def test_node_upsert_with_nodeinfo_still_fills_placeholder(self):
        from django.utils import timezone

        suffix = f"{self.from_node.meshtastic_node_id:08x}"[-4:]
        self._seed_names(long_name=f"Meshtastic {suffix}", short_name=suffix)
        self._nodeinfo_at(timezone.now())
        self._upsert(user={"long_name": "Real Name", "short_name": "REAL"})
        self.assertEqual(self.from_node.long_name, "Real Name")
        self.assertEqual(self.from_node.short_name, "REAL")

    def test_node_upsert_null_last_heard_keeps_stored(self):
        from datetime import timedelta

        from django.utils import timezone

        stored = timezone.now() - timedelta(hours=1)
        self._set_last_heard(stored)
        self._upsert(last_heard=None)
        self.assertEqual(self.from_node.last_heard, stored)

    def test_node_upsert_without_name_fields_skips_nodeinfo_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self._upsert(macaddr="11:22:33:44:55:66")
        self.assertFalse([q for q in ctx.captured_queries if "packets_nodeinfopacket" in q["sql"]])

    def test_node_upsert_with_name_fields_queries_nodeinfo_once(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self._upsert(user={"long_name": "Some Name", "short_name": "SOME"})
        self.assertEqual(len([q for q in ctx.captured_queries if "packets_nodeinfopacket" in q["sql"]]), 1)

    def test_node_upsert_placeholder_never_replaces_real_name(self):
        self._seed_names()
        suffix = f"{self.from_node.meshtastic_node_id:08x}"[-4:]
        self._upsert(user={"long_name": f"Meshtastic {suffix}", "short_name": suffix})
        self.assertEqual(self.from_node.long_name, "TIGERBAWS")
        self.assertEqual(self.from_node.short_name, "TIGR")

    def test_node_upsert_fills_empty_name(self):
        self._seed_names(long_name="", short_name="")
        self._upsert(user={"long_name": "Filled Name", "short_name": "FILL"})
        self.assertEqual(self.from_node.long_name, "Filled Name")
        self.assertEqual(self.from_node.short_name, "FILL")

    def test_node_upsert_fills_placeholder_name(self):
        suffix = f"{self.from_node.meshtastic_node_id:08x}"[-4:]
        self._seed_names(long_name=f"Meshtastic {suffix}", short_name=suffix)
        self._upsert(user={"long_name": "Real Name", "short_name": "REAL"})
        self.assertEqual(self.from_node.long_name, "Real Name")
        self.assertEqual(self.from_node.short_name, "REAL")

    def _set_last_heard(self, value):
        self.from_node.last_heard = value
        self.from_node.save()

    def test_node_upsert_older_last_heard_keeps_stored(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now() - timedelta(minutes=5)
        self._set_last_heard(now)
        self._upsert(last_heard=(now - timedelta(days=1)).isoformat())
        self.assertEqual(self.from_node.last_heard, now)

    def test_node_upsert_newer_last_heard_updates_stored(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        self._set_last_heard(now - timedelta(hours=1))
        self._upsert(last_heard=now.isoformat())
        self.assertEqual(self.from_node.last_heard, now)

    def test_node_upsert_future_last_heard_is_ignored(self):
        from datetime import timedelta

        from django.utils import timezone

        stored = timezone.now() - timedelta(hours=1)
        self._set_last_heard(stored)
        self._upsert(last_heard=(timezone.now() + timedelta(hours=2)).isoformat())
        self.assertEqual(self.from_node.last_heard, stored)

    def test_node_upsert_none_stored_takes_incoming_last_heard(self):
        from datetime import timedelta

        from django.utils import timezone

        self._set_last_heard(None)
        incoming = timezone.now() - timedelta(days=1)
        self._upsert(last_heard=incoming.isoformat())
        self.assertEqual(self.from_node.last_heard, incoming)

    def test_node_upsert_stale_last_heard_keeps_name_and_last_heard(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        self._seed_names()
        self._set_last_heard(now)
        self._nodeinfo_at(now)
        self._upsert(
            user={"long_name": "Old Name", "short_name": "OLD"},
            last_heard=(now - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(self.from_node.long_name, "TIGERBAWS")
        self.assertEqual(self.from_node.last_heard, now)

    def test_node_create_takes_incoming_last_heard_but_not_future(self):
        from datetime import timedelta

        from django.utils import timezone

        from packets.serializers import NodeSerializer

        past = timezone.now() - timedelta(days=1)
        for node_id, value, expected in [
            (0x0A0B0C01, past, past),
            (0x0A0B0C02, timezone.now() + timedelta(hours=2), None),
        ]:
            serializer = NodeSerializer(
                data={
                    "id": node_id,
                    "macaddr": "a0:b3:a9:cf:5a:7b",
                    "user": {"long_name": "New", "short_name": "NEW"},
                    "last_heard": value.isoformat(),
                }
            )
            assert_serializer_valid(serializer)
            node = serializer.save()
            node.refresh_from_db()
            self.assertEqual(node.last_heard, expected)

    def test_node_upsert_zero_position_does_not_overwrite_stored_position(self):
        from django.utils import timezone

        def position(lat, lon):
            return {
                "reported_time": timezone.now().isoformat(),
                "latitude": lat,
                "longitude": lon,
                "altitude": 5.0,
                "meshtastic_location_source": "UNSET",
            }

        self._upsert(position=position(55.9, -3.2))
        self._upsert(position=position(0.0, 0.0))
        self._upsert(position=position(5e-8, -5e-8))  # within the 1e-7 tolerance, like ingest

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.latitude, 55.9)
        self.assertEqual(latest_status.longitude, -3.2)
        self.assertEqual(Position.objects.filter(node=self.from_node).count(), 1)

    def test_node_upsert_zero_position_on_new_node_stores_nothing(self):
        from django.utils import timezone

        self._upsert(
            position={
                "reported_time": timezone.now().isoformat(),
                "latitude": 0.0,
                "longitude": 0.0,
                "altitude": 0.0,
                "meshtastic_location_source": "UNSET",
            }
        )
        self.assertFalse(NodeLatestStatus.objects.filter(node=self.from_node, latitude=0.0).exists())
        self.assertFalse(Position.objects.filter(node=self.from_node).exists())

    def test_node_upsert_v3_rejects_legacy_only_position_field(self):
        from django.utils import timezone

        from packets.serializers import NodeSerializerV3

        data = {
            "id": self.from_node.meshtastic_node_id,
            "position": {
                "reported_time": timezone.now().isoformat(),
                "latitude": 51.5,
                "longitude": -0.12,
                "altitude": 5.0,
                "location_source": "LOC_INTERNAL",
            },
        }

        serializer = NodeSerializerV3(instance=self.from_node, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("position", serializer.errors)

    def test_node_upsert_v3_accepts_meshtastic_fields(self):
        from django.utils import timezone

        from packets.serializers import NodeSerializerV3

        data = {
            "id": self.from_node.meshtastic_node_id,
            "device_metrics": {
                "reported_time": timezone.now().isoformat(),
                "battery_level": 80.0,
                "voltage": 3.8,
                "meshtastic_channel_utilization": 0.1,
                "meshtastic_air_util_tx": 0.2,
                "uptime_seconds": 100,
            },
        }

        serializer = NodeSerializerV3(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.meshtastic_channel_utilization, 0.1)


@override_settings(PACKET_DEDUP_WINDOW_MINUTES=10)
class PacketDeduplicationTest(BasePacketSerializerTestCase):
    """Tests for packet deduplication behavior."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Second observer for multi-observer tests
        cls.observer2 = ManagedNode.objects.create(
            internal_id=uuid4(),
            meshtastic_node_id=999888777,
            name="Test Node 2",
            constellation_id=cls.constellation.id,
            owner=cls.user,
        )
        # Second sender (different node) for cross-sender test
        cls.from_node_b = ObservedNode.objects.create(
            meshtastic_node_id=111222333,
            long_name="From Node B",
            short_name="FRB",
        )

    def test_different_senders_same_packet_id_creates_new_packet(self):
        """Different senders with same packet_id must create separate packets."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data_a = {
            "id": 123,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "From A"},
            "rxTime": base_time,
        }
        data_b = {
            "id": 123,
            "from": self.from_node_b.meshtastic_node_id,
            "fromId": self.from_node_b.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "From B"},
            "rxTime": base_time,
        }

        serializer_a = MessagePacketSerializer(data=data_a, context=self.context)
        assert_serializer_valid(serializer_a)
        packet_a = serializer_a.save()

        serializer_b = MessagePacketSerializer(data=data_b, context=self.context)
        assert_serializer_valid(serializer_b)
        packet_b = serializer_b.save()

        self.assertNotEqual(packet_a.id, packet_b.id)
        self.assertEqual(packet_a.packet_id, 123)
        self.assertEqual(packet_b.packet_id, 123)
        self.assertEqual(packet_a.from_int, self.from_node.meshtastic_node_id)
        self.assertEqual(packet_b.from_int, self.from_node_b.meshtastic_node_id)
        self.assertEqual(packet_a.message_text, "From A")
        self.assertEqual(packet_b.message_text, "From B")

    def test_same_sender_same_packet_id_within_window_reuses_packet(self):
        """Same sender+packet_id within 10 min from another observer reuses packet."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data = {
            "id": 456,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Hello"},
            "rxTime": base_time,
        }
        data_observer2 = {
            "id": 456,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Hello"},
            "rxTime": base_time + 300,  # 5 min later
        }

        ctx1 = {"observer": self.observer}
        ctx2 = {"observer": self.observer2}

        serializer1 = MessagePacketSerializer(data=data, context=ctx1)
        assert_serializer_valid(serializer1)
        packet1 = serializer1.save()

        serializer2 = MessagePacketSerializer(data=data_observer2, context=ctx2)
        assert_serializer_valid(serializer2)
        packet2 = serializer2.save()

        self.assertEqual(packet1.id, packet2.id)
        self.assertEqual(packet1.observations.count(), 2)
        observer_ids = {o.observer_id for o in packet1.observations.all()}
        self.assertEqual(observer_ids, {self.observer.pk, self.observer2.pk})

    def test_same_sender_same_packet_id_after_window_creates_new_packet(self):
        """Same sender+packet_id 10+ min later creates new packet."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data_first = {
            "id": 789,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "First"},
            "rxTime": base_time,
        }

        serializer1 = MessagePacketSerializer(data=data_first, context=self.context)
        assert_serializer_valid(serializer1)
        packet1 = serializer1.save()

        # Second packet rx_time 11 min after first packet's first_reported_time
        first_reported_ts = int(packet1.first_reported_time.timestamp())
        data_second = {
            "id": 789,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Second"},
            "rxTime": first_reported_ts + 660,  # 11 min later
        }

        serializer2 = MessagePacketSerializer(data=data_second, context=self.context)
        assert_serializer_valid(serializer2)
        packet2 = serializer2.save()

        self.assertNotEqual(packet1.id, packet2.id)
        self.assertEqual(packet1.packet_id, 789)
        self.assertEqual(packet2.packet_id, 789)
        self.assertEqual(packet1.message_text, "First")
        self.assertEqual(packet2.message_text, "Second")

    def test_same_observer_same_packet_twice_no_duplicate_observation(self):
        """Same observer reporting same packet twice does not create duplicate observation."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data = {
            "id": 321,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Once"},
            "rxTime": base_time,
        }

        serializer1 = MessagePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer1)
        packet1 = serializer1.save()

        serializer2 = MessagePacketSerializer(data=data, context=self.context)
        assert_serializer_valid(serializer2)
        packet2 = serializer2.save()

        self.assertEqual(packet1.id, packet2.id)
        self.assertEqual(packet1.observations.count(), 1)


class NodeSerializerHwModelTest(BasePacketSerializerTestCase):
    """Hardware model normalisation on node upsert."""

    def test_update_normalises_numeric_hw_model(self):
        serializer = NodeSerializer(
            instance=self.from_node,
            data={"id": self.from_node.meshtastic_node_id, "meshtastic_hw_model": "152"},
            partial=True,
        )
        assert_serializer_valid(serializer)
        serializer.save()
        self.from_node.refresh_from_db()
        self.assertEqual(self.from_node.meshtastic_hw_model, "HELTEC_MESH_POCKET_V2")

    def test_create_normalises_legacy_alias_and_renamed_name(self):
        serializer = NodeSerializer(
            data={"id": 777001, "long_name": "New", "short_name": "NEW", "macaddr": None, "hw_model": "SENSELORA_S3"}
        )
        assert_serializer_valid(serializer)
        node = serializer.save()
        self.assertEqual(node.meshtastic_hw_model, "MAKERFABS_RESERVED")

    def test_unknown_hw_model_number_is_valid_and_stored_as_hw_n(self):
        serializer = NodeSerializer(
            instance=self.from_node,
            data={"id": self.from_node.meshtastic_node_id, "meshtastic_hw_model": "999"},
            partial=True,
        )
        assert_serializer_valid(serializer)
        serializer.save()
        self.from_node.refresh_from_db()
        self.assertEqual(self.from_node.meshtastic_hw_model, "HW_999")

    def test_non_ascii_digit_hw_model_does_not_raise(self):
        serializer = NodeSerializer(
            instance=self.from_node,
            data={"id": self.from_node.meshtastic_node_id, "meshtastic_hw_model": "²"},
            partial=True,
        )
        assert_serializer_valid(serializer)
