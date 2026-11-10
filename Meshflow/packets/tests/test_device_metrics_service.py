from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from nodes.models import DeviceMetrics, NodeLatestStatus, ObservedNode
from packets.services.device_metrics import DeviceMetricsPacketService
from packets.signals import device_metrics_recorded


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
    with patch.object(device_metrics_recorded, "send") as mock_send:
        service.process_packet(packet, observer, observation, user)
    assert DeviceMetrics.objects.count() == initial_count + 1
    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args
    assert kwargs["battery_level"] == float(packet.battery_level)

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.node.meshtastic_node_id == packet.from_int
    assert metrics.battery_level == packet.battery_level
    assert metrics.voltage == packet.voltage
    assert metrics.meshtastic_channel_utilization == packet.meshtastic_channel_utilization
    assert metrics.meshtastic_air_util_tx == packet.meshtastic_air_util_tx
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
    first_reported_time = timezone.now()
    packet = create_device_metrics_packet(reading_time=None)
    # Set first_reported_time directly since it's not in the fixture
    packet.first_reported_time = first_reported_time
    packet.save()

    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    metrics = DeviceMetrics.objects.latest("id")
    # Compare datetimes with a tolerance
    assert abs(metrics.reported_time - first_reported_time) < timedelta(milliseconds=100)


@pytest.mark.django_db
def test_process_device_metrics_packet_partial_stores_null_for_missing(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """A partial packet stores null for the missing fields, in the row and in NodeLatestStatus."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(
        battery_level=None,
        voltage=3.9,
        meshtastic_channel_utilization=None,
        meshtastic_air_util_tx=None,
        uptime_seconds=None,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)

    service.process_packet(packet, observer, observation, create_user())

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.battery_level is None
    assert metrics.voltage == 3.9
    assert metrics.meshtastic_channel_utilization is None
    assert metrics.meshtastic_air_util_tx is None
    assert metrics.uptime_seconds is None

    latest = NodeLatestStatus.objects.get(node=metrics.node)
    assert latest.battery_level is None
    assert latest.voltage == 3.9
    assert latest.meshtastic_channel_utilization is None
    assert latest.meshtastic_air_util_tx is None
    assert latest.uptime_seconds is None


@pytest.mark.django_db
def test_process_device_metrics_packet_all_absent_creates_no_row(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """No reading at all: no DeviceMetrics row, NodeLatestStatus untouched, no signal."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(
        battery_level=None,
        voltage=None,
        meshtastic_channel_utilization=None,
        meshtastic_air_util_tx=None,
        uptime_seconds=None,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    NodeLatestStatus.objects.create(node=node, battery_level=77.0, voltage=4.0)
    before = DeviceMetrics.objects.count()

    with patch.object(device_metrics_recorded, "send") as mock_send:
        service.process_packet(packet, observer, observation, create_user())

    assert DeviceMetrics.objects.count() == before
    latest = NodeLatestStatus.objects.get(node=node)
    assert latest.battery_level == 77.0
    assert latest.voltage == 4.0
    mock_send.assert_not_called()


@pytest.mark.django_db
def test_process_device_metrics_packet_keeps_genuine_zeros(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """A reported 0 stays 0 (a quiet channel is 0% utilisation); only absent fields become null."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(
        battery_level=0,
        voltage=3.2,
        meshtastic_channel_utilization=0.0,
        meshtastic_air_util_tx=None,
        uptime_seconds=0,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)

    service.process_packet(packet, observer, observation, create_user())

    metrics = DeviceMetrics.objects.latest("id")
    assert metrics.battery_level == 0
    assert metrics.voltage == 3.2
    assert metrics.meshtastic_channel_utilization == 0.0
    assert metrics.meshtastic_air_util_tx is None
    assert metrics.uptime_seconds == 0
    latest = NodeLatestStatus.objects.get(node=metrics.node)
    assert latest.battery_level == 0
    assert latest.meshtastic_channel_utilization == 0.0
    assert latest.meshtastic_air_util_tx is None


@pytest.mark.django_db
def test_process_device_metrics_packet_signal_battery_none(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """A missing battery reading reaches the signal as None, not 0."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(battery_level=None)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)

    with patch.object(device_metrics_recorded, "send") as mock_send:
        service.process_packet(packet, observer, observation, create_user())
    assert mock_send.call_args.kwargs["battery_level"] is None


@pytest.mark.django_db
def test_update_node_last_heard(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test that the node's last_heard timestamp is updated."""
    service = DeviceMetricsPacketService()
    first_reported_time = timezone.now()
    packet = create_device_metrics_packet()
    packet.first_reported_time = first_reported_time
    packet.save()

    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create the from_node with an old last_heard
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    old_time = timezone.now() - timezone.timedelta(days=1)
    from_node.last_heard = old_time
    from_node.save()

    service.process_packet(packet, observer, observation, user)

    # Verify the node's last_heard was updated
    from_node.refresh_from_db()
    assert from_node.last_heard == first_reported_time


@pytest.mark.django_db
def test_process_device_metrics_packet_updates_nodelateststatus(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    """Test that processing a device metrics packet updates NodeLatestStatus."""
    service = DeviceMetricsPacketService()
    packet = create_device_metrics_packet(
        battery_level=88.0,
        voltage=4.1,
        meshtastic_channel_utilization=0.15,
        meshtastic_air_util_tx=0.25,
        uptime_seconds=7200,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    metrics = DeviceMetrics.objects.latest("id")
    observed_node = metrics.node

    latest_status = NodeLatestStatus.objects.get(node=observed_node)
    assert latest_status.battery_level == 88.0
    assert latest_status.voltage == 4.1
    assert latest_status.meshtastic_channel_utilization == 0.15
    assert latest_status.meshtastic_air_util_tx == 0.25
    assert latest_status.uptime_seconds == 7200
    assert latest_status.metrics_reported_time is not None
    assert latest_status.meshtastic_inferred_max_hops == observation.hop_start
