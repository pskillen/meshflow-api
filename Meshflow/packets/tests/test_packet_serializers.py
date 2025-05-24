"""Tests for packet serializers."""

from datetime import datetime, timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation, MessageChannel
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
    PrefetchedPacketObservationSerializer, # Added import
    convert_timestamp,
)
from packets.models import RawPacket, PacketObservation # Added import
from django.utils import timezone # Added import

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
            node_id=456789, node_id_str=meshtastic_id_to_hex(456789), long_name="From Node"
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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

        # Verify observation creation
        self.assertEqual(packet.observations.count(), 1)
        observation = packet.observations.first()
        self.assertEqual(observation.observer, self.observer)

    def test_create_message_packet_existing_packet_does_not_update_first_observed_time(self):
        """Test that first_observed_time is not updated for an existing message packet."""
        initial_rx_time = 1672531200  # 2023-01-01 00:00:00 UTC
        data1 = {
            "id": 12345, # Unique packet ID for this test
            "from": self.from_node.node_id,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "First message"},
            "rxTime": initial_rx_time,
        }

        serializer1 = MessagePacketSerializer(data=data1, context=self.context)
        assert_serializer_valid(serializer1)
        packet = serializer1.save()
        original_first_observed_time = packet.first_observed_time
        self.assertEqual(original_first_observed_time, convert_timestamp(initial_rx_time))

        # Simulate a second observation for the same packet with a different rxTime
        later_rx_time = 1672534800  # 2023-01-01 01:00:00 UTC
        data2 = {
            "id": 12345, # Same packet ID
            "from": self.from_node.node_id,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Duplicate message, different time"},
            "rxTime": later_rx_time,
        }
        # Use a different observer for the second observation to make it unique
        observer2 = ManagedNode.objects.create(
            internal_id=uuid4(), node_id=99999, name="Observer 2", constellation=self.constellation, owner=self.user
        )
        context2 = {"observer": observer2}
        serializer2 = MessagePacketSerializer(data=data2, context=context2)
        assert_serializer_valid(serializer2)
        updated_packet = serializer2.save() # This should retrieve the existing packet

        self.assertEqual(updated_packet.id, packet.id) # Ensure it's the same packet object
        self.assertEqual(updated_packet.first_observed_time, original_first_observed_time)
        self.assertNotEqual(updated_packet.first_observed_time, convert_timestamp(later_rx_time))
        self.assertEqual(updated_packet.observations.count(), 2) # Should have two observations now

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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

    def test_create_position_packet_existing_packet_does_not_update_first_observed_time(self):
        """Test that first_observed_time is not updated for an existing position packet."""
        initial_rx_time = 1672531200
        data1 = {
            "id": 54321, # Unique packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {"latitude": 10.0, "longitude": 20.0},
            },
            "rxTime": initial_rx_time,
        }
        serializer1 = PositionPacketSerializer(data=data1, context=self.context)
        assert_serializer_valid(serializer1)
        packet = serializer1.save()
        original_first_observed_time = packet.first_observed_time
        self.assertEqual(original_first_observed_time, convert_timestamp(initial_rx_time))

        later_rx_time = 1672534800
        data2 = {
            "id": 54321, # Same packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {"latitude": 10.1, "longitude": 20.1}, # slightly different data
            },
            "rxTime": later_rx_time,
        }
        observer2 = ManagedNode.objects.create(
            internal_id=uuid4(), node_id=99998, name="Observer 2 Pos", constellation=self.constellation, owner=self.user
        )
        context2 = {"observer": observer2}
        serializer2 = PositionPacketSerializer(data=data2, context=context2)
        assert_serializer_valid(serializer2)
        updated_packet = serializer2.save()

        self.assertEqual(updated_packet.id, packet.id)
        self.assertEqual(updated_packet.first_observed_time, original_first_observed_time)
        self.assertEqual(updated_packet.observations.count(), 2)


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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

    def test_create_node_info_packet_existing_packet_does_not_update_first_observed_time(self):
        """Test that first_observed_time is not updated for an existing node info packet."""
        initial_rx_time = 1672531200
        data1 = {
            "id": 67890, # Unique packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {"id": "!abcdef", "longName": "Node Alpha"},
            },
            "rxTime": initial_rx_time,
        }
        serializer1 = NodeInfoPacketSerializer(data=data1, context=self.context)
        assert_serializer_valid(serializer1)
        packet = serializer1.save()
        original_first_observed_time = packet.first_observed_time
        self.assertEqual(original_first_observed_time, convert_timestamp(initial_rx_time))

        later_rx_time = 1672534800
        data2 = {
            "id": 67890, # Same packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {"id": "!abcdef", "longName": "Node Alpha Updated"},
            },
            "rxTime": later_rx_time,
        }
        observer2 = ManagedNode.objects.create(
            internal_id=uuid4(), node_id=99997, name="Observer 2 NI", constellation=self.constellation, owner=self.user
        )
        context2 = {"observer": observer2}
        serializer2 = NodeInfoPacketSerializer(data=data2, context=context2)
        assert_serializer_valid(serializer2)
        updated_packet = serializer2.save()

        self.assertEqual(updated_packet.id, packet.id)
        self.assertEqual(updated_packet.first_observed_time, original_first_observed_time)
        self.assertEqual(updated_packet.observations.count(), 2)


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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

    def test_create_device_metrics_packet_existing_packet_does_not_update_first_observed_time(self):
        """Test that first_observed_time is not updated for an existing device metrics packet."""
        initial_rx_time = 1672531200
        data1 = {
            "id": 78901, # Unique packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"deviceMetrics": {"batteryLevel": 80.0}, "time": initial_rx_time},
            },
            "rxTime": initial_rx_time,
        }
        serializer1 = DeviceMetricsPacketSerializer(data=data1, context=self.context)
        assert_serializer_valid(serializer1)
        packet = serializer1.save()
        original_first_observed_time = packet.first_observed_time
        self.assertEqual(original_first_observed_time, convert_timestamp(initial_rx_time))

        later_rx_time = 1672534800
        data2 = {
            "id": 78901, # Same packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"deviceMetrics": {"batteryLevel": 75.0}, "time": later_rx_time},
            },
            "rxTime": later_rx_time,
        }
        observer2 = ManagedNode.objects.create(
            internal_id=uuid4(), node_id=99996, name="Observer 2 DM", constellation=self.constellation, owner=self.user
        )
        context2 = {"observer": observer2}
        serializer2 = DeviceMetricsPacketSerializer(data=data2, context=context2)
        assert_serializer_valid(serializer2)
        updated_packet = serializer2.save()

        self.assertEqual(updated_packet.id, packet.id)
        self.assertEqual(updated_packet.first_observed_time, original_first_observed_time)
        self.assertEqual(updated_packet.observations.count(), 2)


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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

    def test_create_local_stats_packet_existing_packet_does_not_update_first_observed_time(self):
        """Test that first_observed_time is not updated for an existing local stats packet."""
        initial_rx_time = 1672531200
        data1 = {
            "id": 89012, # Unique packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"localStats": {"uptimeSeconds": 1000}, "time": initial_rx_time},
            },
            "rxTime": initial_rx_time,
        }
        serializer1 = LocalStatsPacketSerializer(data=data1, context=self.context)
        assert_serializer_valid(serializer1)
        packet = serializer1.save()
        original_first_observed_time = packet.first_observed_time
        self.assertEqual(original_first_observed_time, convert_timestamp(initial_rx_time))

        later_rx_time = 1672534800
        data2 = {
            "id": 89012, # Same packet ID
            "from": self.from_node.node_id,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"localStats": {"uptimeSeconds": 2000}, "time": later_rx_time},
            },
            "rxTime": later_rx_time,
        }
        observer2 = ManagedNode.objects.create(
            internal_id=uuid4(), node_id=99995, name="Observer 2 LS", constellation=self.constellation, owner=self.user
        )
        context2 = {"observer": observer2}
        serializer2 = LocalStatsPacketSerializer(data=data2, context=context2)
        assert_serializer_valid(serializer2)
        updated_packet = serializer2.save()

        self.assertEqual(updated_packet.id, packet.id)
        self.assertEqual(updated_packet.first_observed_time, original_first_observed_time)
        self.assertEqual(updated_packet.observations.count(), 2)


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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

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
        expected_first_observed_time = convert_timestamp(data["rxTime"])
        self.assertEqual(packet.first_observed_time, expected_first_observed_time)

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


class PrefetchedPacketObservationSerializerTest(BasePacketSerializerTestCase):
    """Tests for PrefetchedPacketObservationSerializer."""

    def test_serialization_includes_first_observed_time(self):
        """Test that first_observed_time from the related packet is included."""
        # Create a RawPacket with a specific first_observed_time
        expected_time = timezone.now()
        # Ensure all required fields for RawPacket are provided
        raw_packet = RawPacket.objects.create(
            packet_id=999888777,
            from_int=12345, # Example value
            # from_str will be set automatically if from_int is provided and model save is called
            # or if using a fixture that handles this. For direct creation, ensure it's handled or nullable.
            # Assuming from_str is not strictly required here if from_int is set, or handled by model.
            first_observed_time=expected_time
        )

        # Create a PacketObservation linked to this RawPacket
        # self.observer is available from BasePacketSerializerTestCase
        packet_observation = PacketObservation.objects.create(
            packet=raw_packet,
            observer=self.observer,
            rx_time=timezone.now(), # This is rx_time of the observation itself
            # Ensure other required fields for PacketObservation are set
            channel=None, # Assuming channel can be null or provide a mock
        )

        # Serialize the PacketObservation
        serializer = PrefetchedPacketObservationSerializer(packet_observation)
        serialized_data = serializer.data

        # Assertions
        self.assertIn("first_observed_time", serialized_data)
        # DRF DateTimeField typically renders to ISO 8601 string format.
        # The default format is 'YYYY-MM-DDTHH:MM:SS.ffffffZ' or similar.
        # Using .isoformat() and then ensuring it matches DRF's typical output.
        # DRF output for DateTimeField is timezone aware and usually ends with 'Z' for UTC.
        expected_iso_format = expected_time.isoformat()
        if expected_iso_format.endswith("+00:00"):
            expected_iso_format = expected_iso_format[:-6] + "Z"
        
        self.assertEqual(serialized_data["first_observed_time"], expected_iso_format)

    def test_serialization_with_prefetched_observer_details(self):
        """Test that observer details are correctly serialized (existing functionality)."""
        raw_packet = RawPacket.objects.create(
            packet_id=111222333, from_int=67890, first_observed_time=timezone.now()
        )
        # Create an ObservedNode that corresponds to self.observer (ManagedNode)
        # This is for testing the get_long_name/get_short_name logic in ObserverSerializer
        ObservedNode.objects.update_or_create(
            node_id=self.observer.node_id,
            defaults={
                'node_id_str': meshtastic_id_to_hex(self.observer.node_id),
                'long_name': "Observer Long Name",
                'short_name': "OBSLN"
            }
        )
        
        packet_observation = PacketObservation.objects.create(
            packet=raw_packet, observer=self.observer, rx_time=timezone.now()
        )

        # Simulate prefetching for context (as the serializer expects for observer_nodes_map)
        observer_nodes_map = {
            self.observer.node_id: ObservedNode.objects.get(node_id=self.observer.node_id)
        }
        serializer_context = {"observer_nodes_map": observer_nodes_map}
        
        serializer = PrefetchedPacketObservationSerializer(packet_observation, context=serializer_context)
        serialized_data = serializer.data

        self.assertIn("observer", serialized_data)
        self.assertEqual(serialized_data["observer"]["long_name"], "Observer Long Name")
        self.assertEqual(serialized_data["observer"]["short_name"], "OBSLN")
        self.assertEqual(serialized_data["observer"]["node_id_str"], meshtastic_id_to_hex(self.observer.node_id))
