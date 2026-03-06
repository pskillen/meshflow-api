from django.utils import timezone

import pytest

from nodes.models import LocationSource, NodeLatestStatus, Position
from packets.services.position import PositionPacketService


@pytest.mark.django_db
def test_position_service_init():
    """Test PositionPacketService initialization."""
    service = PositionPacketService()
    assert isinstance(service, PositionPacketService)


@pytest.mark.django_db
def test_process_packet_invalid_type(create_raw_packet, create_managed_node, create_packet_observation, create_user):
    """Test processing a packet with an invalid type."""
    service = PositionPacketService()
    packet = create_raw_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    with pytest.raises(ValueError, match="Packet must be a PositionPacket"):
        service.process_packet(packet, observer, observation, user)


@pytest.mark.django_db
def test_process_position_packet(create_position_packet, create_managed_node, create_packet_observation, create_user):
    """Test processing a position packet."""
    service = PositionPacketService()
    packet = create_position_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    initial_count = Position.objects.count()
    service.process_packet(packet, observer, observation, user)
    assert Position.objects.count() == initial_count + 1

    position = Position.objects.latest("id")
    assert position.node.node_id == packet.from_int
    assert position.latitude == packet.latitude
    assert position.longitude == packet.longitude
    assert position.altitude == packet.altitude
    assert position.heading == packet.heading
    assert position.location_source == packet.location_source
    assert position.precision_bits == packet.precision_bits
    assert position.ground_speed == packet.ground_speed
    assert position.ground_track == packet.ground_track


@pytest.mark.django_db
def test_process_position_packet_with_position_time(
    create_position_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a position packet with a position time."""
    service = PositionPacketService()
    position_time = timezone.now()
    packet = create_position_packet(position_time=position_time)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    position = Position.objects.latest("id")
    assert position.reported_time == position_time


@pytest.mark.django_db
def test_process_position_packet_without_position_time(
    create_position_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a position packet without a position time."""
    service = PositionPacketService()
    first_reported_time = timezone.now()
    packet = create_position_packet(position_time=None)
    # Set first_reported_time directly since it's not in the fixture
    packet.first_reported_time = first_reported_time
    packet.save()

    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    position = Position.objects.latest("id")
    assert position.reported_time == first_reported_time


@pytest.mark.django_db
def test_process_position_packet_without_location_source(
    create_position_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a position packet without a location source."""
    service = PositionPacketService()
    packet = create_position_packet(location_source=None)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    position = Position.objects.latest("id")
    assert position.location_source == LocationSource.UNSET


@pytest.mark.django_db
def test_process_position_packet_updates_nodelateststatus(
    create_position_packet, create_managed_node, create_packet_observation, create_user
):
    """Test that processing a position packet updates NodeLatestStatus."""
    service = PositionPacketService()
    packet = create_position_packet(
        latitude=12.34,
        longitude=56.78,
        altitude=100.0,
        heading=45.0,
        ground_speed=5.0,
        ground_track=90.0,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    from_node = packet.from_int
    observed_node = Position.objects.latest("id").node
    assert observed_node.node_id == from_node

    latest_status = NodeLatestStatus.objects.get(node=observed_node)
    assert latest_status.latitude == 12.34
    assert latest_status.longitude == 56.78
    assert latest_status.altitude == 100.0
    assert latest_status.heading == 45.0
    assert latest_status.ground_speed == 5.0
    assert latest_status.ground_track == 90.0
    assert latest_status.position_reported_time is not None
