import pytest
from rest_framework.test import APIClient

from packets.models import (
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    LocalStatsPacket,
    LocationSource,
    MessagePacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    RawPacket,
    RoleSource,
)
from packets.serializers import (
    BasePacketSerializer,
    DeviceMetricsPacketSerializer,
    DeviceMetricsSerializer,
    MessagePacketSerializer,
    NodeInfoPacketSerializer,
    NodeSerializer,
    PacketIngestSerializer,
    PositionPacketSerializer,
    PositionSerializer,
)


@pytest.mark.django_db
def test_base_packet_serializer_valid_data(create_raw_packet):
    """Test base packet serializer with valid data."""
    packet = create_raw_packet()
    serializer = BasePacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["from_int"] == 987654321
    assert data["from_str"] == "!3ade68b1"
    assert data["to_int"] == 123456789
    assert data["to_str"] == "!75bcd15"
    assert data["port_num"] == "TEXT_MESSAGE_APP"


@pytest.mark.django_db
def test_message_packet_serializer_valid_data(create_message_packet):
    """Test message packet serializer with valid data."""
    packet = create_message_packet()
    serializer = MessagePacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["message_text"] == "Test message"
    assert data["reply_packet_id"] is None
    assert data["emoji"] is False


@pytest.mark.django_db
def test_position_packet_serializer_valid_data(create_position_packet):
    """Test position packet serializer with valid data."""
    packet = create_position_packet()
    serializer = PositionPacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["latitude"] == 0.0
    assert data["longitude"] == 0.0
    assert data["altitude"] == 0.0
    assert data["heading"] == 0.0
    assert data["location_source"] == LocationSource.GPS
    assert data["precision_bits"] == 32
    assert data["ground_speed"] == 0.0
    assert data["ground_track"] == 0.0


@pytest.mark.django_db
def test_node_info_packet_serializer_valid_data(create_node_info_packet):
    """Test node info packet serializer with valid data."""
    packet = create_node_info_packet()
    serializer = NodeInfoPacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["node_id"] == "!3ade68b1"
    assert data["short_name"] == "TEST"
    assert data["long_name"] == "Test Node"
    assert data["hw_model"] == "T-Beam"
    assert data["sw_version"] == "2.0.0"
    assert data["mac_address"] == "00:11:22:33:44:55"
    assert data["role"] == RoleSource.ROUTER


@pytest.mark.django_db
def test_device_metrics_packet_serializer_valid_data(create_device_metrics_packet):
    """Test device metrics packet serializer with valid data."""
    packet = create_device_metrics_packet()
    serializer = DeviceMetricsPacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["battery_level"] == 95.5
    assert data["voltage"] == 3.7
    assert data["channel_utilization"] == 0.1
    assert data["air_util_tx"] == 0.2
    assert data["uptime_seconds"] == 3600


@pytest.mark.django_db
def test_packet_ingest_serializer_valid_data(create_raw_packet):
    """Test packet ingest serializer with valid data."""
    packet = create_raw_packet()
    serializer = PacketIngestSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["from_int"] == 987654321
    assert data["from_str"] == "!3ade68b1"
    assert data["to_int"] == 123456789
    assert data["to_str"] == "!75bcd15"
    assert data["port_num"] == "TEXT_MESSAGE_APP"


@pytest.mark.django_db
def test_position_serializer_valid_data(create_position_packet):
    """Test position serializer with valid data."""
    packet = create_position_packet()
    serializer = PositionSerializer(packet)
    data = serializer.data
    assert data["latitude"] == 0.0
    assert data["longitude"] == 0.0
    assert data["altitude"] == 0.0
    assert data["heading"] == 0.0
    assert data["location_source"] == LocationSource.GPS
    assert data["precision_bits"] == 32
    assert data["ground_speed"] == 0.0
    assert data["ground_track"] == 0.0


@pytest.mark.django_db
def test_device_metrics_serializer_valid_data(create_device_metrics_packet):
    """Test device metrics serializer with valid data."""
    packet = create_device_metrics_packet()
    serializer = DeviceMetricsSerializer(packet)
    data = serializer.data
    assert data["battery_level"] == 95.5
    assert data["voltage"] == 3.7
    assert data["channel_utilization"] == 0.1
    assert data["air_util_tx"] == 0.2
    assert data["uptime_seconds"] == 3600


@pytest.mark.django_db
def test_node_serializer_valid_data(create_node_info_packet):
    """Test node serializer with valid data."""
    packet = create_node_info_packet()
    serializer = NodeSerializer(packet)
    data = serializer.data
    assert data["node_id"] == "!3ade68b1"
    assert data["short_name"] == "TEST"
    assert data["long_name"] == "Test Node"
    assert data["hw_model"] == "T-Beam"
    assert data["sw_version"] == "2.0.0"
    assert data["mac_address"] == "00:11:22:33:44:55"
    assert data["role"] == RoleSource.ROUTER


@pytest.mark.django_db
def test_local_stats_packet_serializer_valid_data(create_local_stats_packet):
    """Test local stats packet serializer with valid data."""
    packet = create_local_stats_packet()
    serializer = LocalStatsPacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["uptime_seconds"] == 3600
    assert data["channel_utilization"] == 0.1
    assert data["air_util_tx"] == 0.2
    assert data["num_packets_tx"] == 1000
    assert data["num_packets_rx"] == 2000
    assert data["num_packets_rx_bad"] == 50
    assert data["num_online_nodes"] == 10
    assert data["num_total_nodes"] == 20
    assert data["num_rx_dupe"] == 100


@pytest.mark.django_db
def test_environment_metrics_packet_serializer_valid_data(create_environment_metrics_packet):
    """Test environment metrics packet serializer with valid data."""
    packet = create_environment_metrics_packet()
    serializer = EnvironmentMetricsPacketSerializer(packet)
    data = serializer.data
    assert data["packet_id"] == 123456789
    assert data["temperature"] == 25.5
    assert data["relative_humidity"] == 50.0
    assert data["barometric_pressure"] == 1013.25
    assert data["gas_resistance"] == 1000.0
    assert data["iaq"] == 50.0


@pytest.mark.django_db
def test_packet_observation_serializer_valid_data(create_packet_observation):
    """Test packet observation serializer with valid data."""
    observation = create_packet_observation()
    serializer = PacketObservationSerializer(observation)
    data = serializer.data
    assert data["channel"] == 1
    assert data["hop_limit"] == 3
    assert data["hop_start"] == 3
    assert data["rx_rssi"] == -60.0
    assert data["rx_snr"] == 10.0
    assert data["relay_node"] is None
