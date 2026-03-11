"""Tests for packet serializers."""

from datetime import datetime, timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation, MessageChannel
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode
from packets.models import (
    DeviceMetricsPacket,
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
            node_id=123456789,
            name="Test Node",
            constellation_id=cls.constellation.id,
            owner=cls.user,
        )

        cls.from_node = ObservedNode.objects.create(
            node_id=456789,
            node_id_str=meshtastic_id_to_hex(456789),
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
            "id": 123456789,
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
        # Assign to observer's channel_0
        self.observer.channel_0 = message_channel
        self.observer.save()

        data = {
            "id": 987654321,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
            "id": 123456789,
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
        self.assertEqual(packet.from_int, 1623194643)
        self.assertEqual(packet.to_int, 123456789)
        # Verify PacketObservation was created
        self.assertEqual(packet.observations.count(), 1)
        self.assertEqual(packet.observations.first().observer, self.observer)

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


class NodeSerializerTest(BasePacketSerializerTestCase):
    """Tests for NodeSerializer."""

    def test_node_upsert_with_position_updates_nodelateststatus(self):
        """Test that creating a node with position updates NodeLatestStatus."""
        from django.utils import timezone

        data = {
            "id": self.from_node.node_id,
            "id_str": self.from_node.node_id_str,
            "long_name": "Updated Node",
            "short_name": "UPD",
            "position": {
                "reported_time": timezone.now().isoformat(),
                "latitude": 40.7128,
                "longitude": -74.0060,
                "altitude": 10.0,
                "heading": 0.0,
                "location_source": "UNSET",
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
            "id": self.from_node.node_id,
            "id_str": self.from_node.node_id_str,
            "long_name": "Updated Node",
            "short_name": "UPD",
            "device_metrics": {
                "reported_time": timezone.now().isoformat(),
                "battery_level": 85.0,
                "voltage": 3.9,
                "channel_utilization": 0.2,
                "air_util_tx": 0.3,
                "uptime_seconds": 10000,
            },
        }

        serializer = NodeSerializer(instance=self.from_node, data=data, partial=True)
        assert_serializer_valid(serializer)
        serializer.save()

        latest_status = NodeLatestStatus.objects.get(node=self.from_node)
        self.assertEqual(latest_status.battery_level, 85.0)
        self.assertEqual(latest_status.voltage, 3.9)
        self.assertEqual(latest_status.channel_utilization, 0.2)
        self.assertEqual(latest_status.air_util_tx, 0.3)
        self.assertEqual(latest_status.uptime_seconds, 10000)
        self.assertIsNotNone(latest_status.metrics_reported_time)


@override_settings(PACKET_DEDUP_WINDOW_MINUTES=10)
class PacketDeduplicationTest(BasePacketSerializerTestCase):
    """Tests for packet deduplication behavior."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Second observer for multi-observer tests
        cls.observer2 = ManagedNode.objects.create(
            internal_id=uuid4(),
            node_id=999888777,
            name="Test Node 2",
            constellation_id=cls.constellation.id,
            owner=cls.user,
        )
        # Second sender (different node) for cross-sender test
        cls.from_node_b = ObservedNode.objects.create(
            node_id=111222333,
            node_id_str=meshtastic_id_to_hex(111222333),
            long_name="From Node B",
            short_name="FRB",
        )

    def test_different_senders_same_packet_id_creates_new_packet(self):
        """Different senders with same packet_id must create separate packets."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data_a = {
            "id": 123,
            "from": self.from_node.node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "From A"},
            "rxTime": base_time,
        }
        data_b = {
            "id": 123,
            "from": self.from_node_b.node_id,
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
        self.assertEqual(packet_a.from_int, self.from_node.node_id)
        self.assertEqual(packet_b.from_int, self.from_node_b.node_id)
        self.assertEqual(packet_a.message_text, "From A")
        self.assertEqual(packet_b.message_text, "From B")

    def test_same_sender_same_packet_id_within_window_reuses_packet(self):
        """Same sender+packet_id within 10 min from another observer reuses packet."""
        from django.utils import timezone as django_tz

        base_time = int(django_tz.now().timestamp())
        data = {
            "id": 456,
            "from": self.from_node.node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Hello"},
            "rxTime": base_time,
        }
        data_observer2 = {
            "id": 456,
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
            "from": self.from_node.node_id,
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
