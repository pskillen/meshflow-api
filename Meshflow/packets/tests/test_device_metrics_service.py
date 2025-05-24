from datetime import timedelta

from django.utils import timezone

import pytest

from nodes.models import DeviceMetrics, ObservedNode
from packets.services.device_metrics import DeviceMetricsPacketService


@pytest.mark.django_db
def test_device_metrics_service_init():
    """Test DeviceMetricsPacketService initialization."""
    service = DeviceMetricsPacketService()
    assert isinstance(service, DeviceMetricsPacketService)


@pytest.mark.django_db
def test_process_packet_invalid_type(create_raw_packet, create_managed_node, create_packet_observation, create_user):
    """Test processing a packet with an invalid type."""
    service = DeviceMetricsPacketService()
    packet = create_raw_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    with pytest.raises(ValueError, match="Packet must be a DeviceMetricsPacket"):
        service.process_packet(packet, observer, observation, user)


@pytest.mark.django_db
def test_process_device_metrics_packet(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a device metrics packet."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    initial_count = DeviceMetrics.objects.count()
    service.process_packet(packet, observer, observation, user)
    assert DeviceMetrics.objects.count() == initial_count + 1

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.node.node_id == packet.from_int
    assert metrics.battery_level == packet.battery_level
    assert metrics.voltage == packet.voltage
    assert metrics.channel_utilization == packet.channel_utilization
    assert metrics.air_util_tx == packet.air_util_tx
    assert metrics.uptime_seconds == packet.uptime_seconds


@pytest.mark.django_db
def test_process_device_metrics_packet_with_reading_time(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a device metrics packet with a reading time."""
    service = DeviceMetricsPacketService()
    reading_time = timezone.now()
    packet = create_device_metrics_packet(reading_time=reading_time)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.reported_time == reading_time


@pytest.mark.django_db
def test_process_device_metrics_packet_without_reading_time(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a device metrics packet without a reading time."""
    service = DeviceMetricsPacketService()
    first_observed_time = timezone.now()
    packet = create_device_metrics_packet(reading_time=None)
    # Set first_observed_time directly since it's not in the fixture
    packet.first_observed_time = first_observed_time
    packet.save()

    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    metrics = DeviceMetrics.objects.latest("id")
    # Compare datetimes with a tolerance
    assert abs(metrics.reported_time - first_observed_time) < timedelta(milliseconds=100)


@pytest.mark.django_db
def test_process_device_metrics_packet_with_null_values(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a device metrics packet with null values."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(
        battery_level=None, voltage=None, channel_utilization=None, air_util_tx=None, uptime_seconds=None
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.battery_level == 0.0
    assert metrics.voltage == 0.0
    assert metrics.channel_utilization == 0.0
    assert metrics.air_util_tx == 0.0
    assert metrics.uptime_seconds == 0


@pytest.mark.django_db
def test_update_node_last_heard(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test that the node's last_heard timestamp is updated."""
    service = DeviceMetricsPacketService()
    first_observed_time = timezone.now()
    packet = create_device_metrics_packet()
    packet.first_observed_time = first_observed_time
    packet.save()

    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create the from_node with an old last_heard
    from_node = ObservedNode.objects.get_or_create(node_id=packet.from_int)[0]
    old_time = timezone.now() - timezone.timedelta(days=1)
    from_node.last_heard = old_time
    from_node.save()

    service.process_packet(packet, observer, observation, user)

    # Verify the node's last_heard was updated
    from_node.refresh_from_db()
    assert from_node.last_heard == first_observed_time
