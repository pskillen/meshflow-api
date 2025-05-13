from django.utils import timezone

import pytest

from constellations.tests.conftest import constellation_data, create_constellation  # noqa: F401
from nodes.tests.conftest import create_managed_node, managed_node_data  # noqa: F401
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
from users.tests.conftest import create_user  # noqa: F401


@pytest.fixture
def raw_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "TEXT_MESSAGE_APP",
    }


@pytest.fixture
def message_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "TEXT_MESSAGE_APP",
        "message_text": "Test message",
        "reply_packet_id": None,
        "emoji": False,
    }


@pytest.fixture
def position_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "POSITION_APP",
        "latitude": 0.0,
        "longitude": 0.0,
        "altitude": 0.0,
        "heading": 0.0,
        "location_source": LocationSource.INTERNAL,
        "precision_bits": 32,
        "position_time": None,
        "ground_speed": 0.0,
        "ground_track": 0.0,
    }


@pytest.fixture
def node_info_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "NODEINFO_APP",
        "node_id": "!3ade68b1",
        "short_name": "TEST",
        "long_name": "Test Node",
        "hw_model": "T-Beam",
        "sw_version": "2.0.0",
        "public_key": None,
        "mac_address": "00:11:22:33:44:55",
        "role": RoleSource.ROUTER,
    }


@pytest.fixture
def device_metrics_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "TELEMETRY_APP",
        "reading_time": timezone.now(),
        "battery_level": 95.5,
        "voltage": 3.7,
        "channel_utilization": 0.1,
        "air_util_tx": 0.2,
        "uptime_seconds": 3600,
    }


@pytest.fixture
def local_stats_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "TELEMETRY_APP",
        "reading_time": timezone.now(),
        "uptime_seconds": 3600,
        "channel_utilization": 0.1,
        "air_util_tx": 0.2,
        "num_packets_tx": 1000,
        "num_packets_rx": 2000,
        "num_packets_rx_bad": 50,
        "num_online_nodes": 10,
        "num_total_nodes": 20,
        "num_rx_dupe": 100,
    }


@pytest.fixture
def environment_metrics_packet_data():
    return {
        "packet_id": 123456789,
        "from_int": 987654321,
        "from_str": "!3ade68b1",
        "to_int": 123456789,
        "to_str": "!75bcd15",
        "port_num": "TELEMETRY_APP",
        "reading_time": timezone.now(),
        "temperature": 25.5,
        "relative_humidity": 50.0,
        "barometric_pressure": 1013.25,
        "gas_resistance": 1000.0,
        "iaq": 50.0,
    }


@pytest.fixture
def create_raw_packet(raw_packet_data):
    def make_packet(**kwargs):
        data = raw_packet_data.copy()
        data.update(kwargs)
        return RawPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_message_packet(message_packet_data):
    def make_packet(**kwargs):
        data = message_packet_data.copy()
        data.update(kwargs)
        return MessagePacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_position_packet(position_packet_data):
    def make_packet(**kwargs):
        data = position_packet_data.copy()
        data.update(kwargs)
        return PositionPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_node_info_packet(node_info_packet_data):
    def make_packet(**kwargs):
        data = node_info_packet_data.copy()
        data.update(kwargs)
        return NodeInfoPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_device_metrics_packet(device_metrics_packet_data):
    def make_packet(**kwargs):
        data = device_metrics_packet_data.copy()
        data.update(kwargs)
        # Ensure reading_time is always set
        if data.get("reading_time") is None:
            data["reading_time"] = timezone.now()
        return DeviceMetricsPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_local_stats_packet(local_stats_packet_data):
    def make_packet(**kwargs):
        data = local_stats_packet_data.copy()
        data.update(kwargs)
        return LocalStatsPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_environment_metrics_packet(environment_metrics_packet_data):
    def make_packet(**kwargs):
        data = environment_metrics_packet_data.copy()
        data.update(kwargs)
        return EnvironmentMetricsPacket.objects.create(**data)

    return make_packet


@pytest.fixture
def create_packet_observation(create_raw_packet, create_managed_node):  # noqa: F811
    def make_observation(**kwargs):
        packet = kwargs.pop("packet", create_raw_packet())
        observer = kwargs.pop("observer", create_managed_node())
        channel = kwargs.pop("channel", 1)
        return PacketObservation.objects.create(
            packet=packet,
            observer=observer,
            channel=channel,
            hop_limit=3,
            hop_start=3,
            rx_time=timezone.now(),
            rx_rssi=-60.0,
            rx_snr=10.0,
            upload_time=timezone.now(),
            relay_node=None,
            **kwargs,
        )

    return make_observation
