"""Tests for packet serializers."""

from datetime import datetime, timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from constellations.models import Constellation
from nodes.models import ManagedNode, ObservedNode
from packets.models import (
    DeviceMetricsPacket,
    LocalStatsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PositionPacket,
    RoleSource,
)
from packets.serializers import (
    BasePacketSerializer,
    DeviceMetricsPacketSerializer,
    LocalStatsPacketSerializer,
    MessagePacketSerializer,
    NodeInfoPacketSerializer,
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
            internal_id=uuid4(), node_id=123456, name="Test Node", constellation_id=cls.constellation.id, owner=cls.user
        )

        cls.from_node = ObservedNode.objects.create(node_id=456789, long_name="From Node")

    def setUp(self):
        """Set up test context."""
        self.context = {"observer": self.observer}


class BasePacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for BasePacketSerializer."""

    def test_base_packet_serialization(self):
        """Test basic packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
        self.assertEqual(validated_data["from_int"], self.from_node.node_id)
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

    def test_invalid_timestamp(self):
        """Test handling of invalid timestamps."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
            "id": 123,
            "from": self.from_node.node_id,
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
        self.assertEqual(packet.packet_id, 123)
        self.assertEqual(packet.message_text, "Hello, world!")

        # Verify observation creation
        self.assertEqual(packet.observations.count(), 1)
        observation = packet.observations.first()
        self.assertEqual(observation.observer, self.observer)


class PositionPacketSerializerTest(BasePacketSerializerTestCase):
    """Tests for PositionPacketSerializer."""

    def test_position_packet_serialization(self):
        """Test position packet serialization."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
        self.assertEqual(validated_data["location_source"], LocationSource.INTERNAL)
        self.assertEqual(validated_data["precision_bits"], 32)
        self.assertEqual(validated_data["ground_speed"], 5.5)
        self.assertEqual(validated_data["ground_track"], 90.0)

    def test_create_position_packet(self):
        """Test creating a position packet."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {
                    "id": "!789012",
                    "shortName": "TEST",
                    "longName": "Test Node",
                    "hwModel": "TBEAM",
                    "swVersion": "2.0.0",
                    "publicKey": "public_key",
                    "macaddr": "00:11:22:33:44:55",
                    "role": "ROUTER",
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
        self.assertEqual(validated_data["sw_version"], "2.0.0")
        self.assertEqual(validated_data["public_key"], "public_key")
        self.assertEqual(validated_data["mac_address"], "00:11:22:33:44:55")
        self.assertEqual(validated_data["role"], RoleSource.ROUTER)

    def test_create_node_info_packet(self):
        """Test creating a node info packet."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
        self.assertEqual(validated_data["channel_utilization"], 0.5)
        self.assertEqual(validated_data["air_util_tx"], 0.3)
        self.assertEqual(validated_data["uptime_seconds"], 3600)

    def test_create_device_metrics_packet(self):
        """Test creating a device metrics packet."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
        self.assertEqual(validated_data["channel_utilization"], 0.5)
        self.assertEqual(validated_data["air_util_tx"], 0.3)
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
            "from": self.from_node.node_id,
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
        self.assertEqual(packet.channel_utilization, 0.5)


class PacketIngestSerializerTest(BasePacketSerializerTestCase):
    """Tests for PacketIngestSerializer."""

    def test_message_packet_ingest(self):
        """Test ingesting a message packet."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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

    def test_invalid_packet_type(self):
        """Test handling of invalid packet type."""
        data = {
            "id": 123,
            "from": self.from_node.node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {
                "portnum": "INVALID_TYPE",
            },
            "rxTime": 1672531200,
        }

        serializer = PacketIngestSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("Unknown packet type", str(serializer.errors))
