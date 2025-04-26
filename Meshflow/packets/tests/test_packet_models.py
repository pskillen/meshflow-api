import pytest

from packets.models import LocationSource, RoleSource


@pytest.mark.django_db
def test_raw_packet_creation(create_raw_packet):
    """Test raw packet creation."""
    packet = create_raw_packet()
    assert packet.packet_id == 123456789
    assert packet.from_int == 987654321
    assert packet.from_str == "!3ade68b1"
    assert packet.to_int == 123456789
    assert packet.to_str == "!75bcd15"
    assert packet.port_num == "TEXT_MESSAGE_APP"


@pytest.mark.django_db
def test_message_packet_creation(create_message_packet):
    """Test message packet creation."""
    packet = create_message_packet()
    assert packet.packet_id == 123456789
    assert packet.message_text == "Test message"
    assert packet.reply_packet_id is None
    assert packet.emoji is False


@pytest.mark.django_db
def test_position_packet_creation(create_position_packet):
    """Test position packet creation."""
    packet = create_position_packet()
    assert packet.packet_id == 123456789
    assert packet.latitude == 0.0
    assert packet.longitude == 0.0
    assert packet.altitude == 0.0
    assert packet.heading == 0.0
    assert packet.location_source == LocationSource.INTERNAL
    assert packet.precision_bits == 32
    assert packet.ground_speed == 0.0
    assert packet.ground_track == 0.0


@pytest.mark.django_db
def test_node_info_packet_creation(create_node_info_packet):
    """Test node info packet creation."""
    packet = create_node_info_packet()
    assert packet.packet_id == 123456789
    assert packet.node_id == "!3ade68b1"
    assert packet.short_name == "TEST"
    assert packet.long_name == "Test Node"
    assert packet.hw_model == "T-Beam"
    assert packet.sw_version == "2.0.0"
    assert packet.mac_address == "00:11:22:33:44:55"
    assert packet.role == RoleSource.ROUTER


@pytest.mark.django_db
def test_device_metrics_packet_creation(create_device_metrics_packet):
    """Test device metrics packet creation."""
    packet = create_device_metrics_packet()
    assert packet.packet_id == 123456789
    assert packet.battery_level == 95.5
    assert packet.voltage == 3.7
    assert packet.channel_utilization == 0.1
    assert packet.air_util_tx == 0.2
    assert packet.uptime_seconds == 3600


@pytest.mark.django_db
def test_local_stats_packet_creation(create_local_stats_packet):
    """Test local stats packet creation."""
    packet = create_local_stats_packet()
    assert packet.packet_id == 123456789
    assert packet.uptime_seconds == 3600
    assert packet.channel_utilization == 0.1
    assert packet.air_util_tx == 0.2
    assert packet.num_packets_tx == 1000
    assert packet.num_packets_rx == 2000
    assert packet.num_packets_rx_bad == 50
    assert packet.num_online_nodes == 10
    assert packet.num_total_nodes == 20
    assert packet.num_rx_dupe == 100


@pytest.mark.django_db
def test_environment_metrics_packet_creation(create_environment_metrics_packet):
    """Test environment metrics packet creation."""
    packet = create_environment_metrics_packet()
    assert packet.packet_id == 123456789
    assert packet.temperature == 25.5
    assert packet.relative_humidity == 50.0
    assert packet.barometric_pressure == 1013.25
    assert packet.gas_resistance == 1000.0
    assert packet.iaq == 50.0


@pytest.mark.django_db
def test_packet_observation_creation(create_packet_observation):
    """Test packet observation creation."""
    observation = create_packet_observation()
    assert observation.channel == 1
    assert observation.hop_limit == 3
    assert observation.hop_start == 3
    assert observation.rx_rssi == -60.0
    assert observation.rx_snr == 10.0
    assert observation.relay_node is None
