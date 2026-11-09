from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from nodes.models import LocationSource, NodeLatestStatus, ObservedNode, Position
from packets.models import PositionPacket
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
    assert position.node.meshtastic_node_id == packet.from_int
    assert position.latitude == packet.latitude
    assert position.longitude == packet.longitude
    assert position.altitude == packet.altitude
    assert position.heading == packet.heading
    assert position.meshtastic_location_source == packet.meshtastic_location_source
    assert position.meshtastic_precision_bits == packet.meshtastic_precision_bits
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
    packet = create_position_packet(meshtastic_location_source=None)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    service.process_packet(packet, observer, observation, user)

    position = Position.objects.latest("id")
    assert position.meshtastic_location_source == LocationSource.UNSET


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
    assert observed_node.meshtastic_node_id == from_node

    latest_status = NodeLatestStatus.objects.get(node=observed_node)
    assert latest_status.latitude == 12.34
    assert latest_status.longitude == 56.78
    assert latest_status.altitude == 100.0
    assert latest_status.heading == 45.0
    assert latest_status.ground_speed == 5.0
    assert latest_status.ground_track == 90.0
    assert latest_status.position_reported_time is not None


# --- null island / missing coordinates -------------------------------------------------------------


@pytest.fixture
def service_args(create_position_packet, create_managed_node, create_packet_observation, create_user):
    return create_position_packet, create_managed_node, create_packet_observation, create_user


def _process(service_args, **packet_kwargs):
    create_position_packet, create_managed_node, create_packet_observation, create_user = service_args
    packet = create_position_packet(**packet_kwargs)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    PositionPacketService().process_packet(packet, observer, observation, create_user())
    return packet


@pytest.mark.django_db
@pytest.mark.parametrize("lat,lon", [(None, None), (51.5, None), (None, -0.1)])
def test_missing_coordinates_store_no_position(service_args, lat, lon):
    packet = _process(service_args, latitude=lat, longitude=lon)
    assert Position.objects.count() == 0
    assert not NodeLatestStatus.objects.filter(latitude__isnull=False).exists()
    assert ObservedNode.objects.get(meshtastic_node_id=packet.from_int).last_heard is not None


@pytest.mark.django_db
def test_null_island_leaves_existing_status_alone(service_args):
    _process(service_args, latitude=12.34, longitude=56.78)
    assert Position.objects.count() == 1
    node = ObservedNode.objects.get(meshtastic_node_id=987654321)
    node.last_heard = None
    node.save(update_fields=["last_heard"])
    _process(service_args, packet_id=222, latitude=None, longitude=None)
    assert Position.objects.count() == 1
    status = NodeLatestStatus.objects.get(node=node)
    assert (status.latitude, status.longitude) == (12.34, 56.78)
    node.refresh_from_db()
    assert node.last_heard is not None


@pytest.mark.django_db
def test_one_axis_zero_position_is_kept(service_args):
    _process(service_args, latitude=0.0, longitude=12.3)
    position = Position.objects.get()
    assert (position.latitude, position.longitude) == (0.0, 12.3)


@pytest.mark.django_db
@pytest.mark.parametrize("lat,lon", [(None, None), (0.0, 0.0), (5e-8, -5e-8)])
def test_no_usable_position_still_updates_inferred_max_hops(service_args, lat, lon):
    """The null path keeps the packet's hop evidence: POSITION_APP sets the sender's inferred max hops."""
    create_position_packet, create_managed_node, create_packet_observation, create_user = service_args
    packet = create_position_packet(latitude=lat, longitude=lon)
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer, hop_start=4, hop_limit=2)
    PositionPacketService().process_packet(packet, observer, observation, create_user())

    status = NodeLatestStatus.objects.get(node__meshtastic_node_id=packet.from_int)
    assert status.meshtastic_inferred_max_hops == 4
    assert status.meshtastic_inferred_max_hops_source == "POSITION_APP"
    assert Position.objects.count() == 0


@pytest.mark.django_db
def test_packet_already_stored_at_null_island_writes_no_position(service_args):
    """A packet stored at 0,0 before deploy can come back through the dedup window: the service must not use it."""
    _process(service_args, latitude=0.0, longitude=0.0)
    assert Position.objects.count() == 0
    assert not NodeLatestStatus.objects.filter(latitude__isnull=False).exists()


# --- ingest through the view -----------------------------------------------------------------------

NODE = 0x1A2B3C4D


@pytest.fixture
def feeder(create_node_auth):
    auth = create_node_auth()
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=auth.api_key.key)
    return client, auth.node


def _ingest(feeder, position, packet_id=5001):
    client, node = feeder
    url = reverse("meshtastic-packet-ingest", kwargs={"node_id": node.meshtastic_node_id})
    return client.post(
        url,
        {
            "id": packet_id,
            "from": NODE,
            "to": 0xFFFFFFFF,
            "decoded": {"portnum": "POSITION_APP", "position": position},
            "rxTime": 1672531200,
            "hopStart": 3,
            "hopLimit": 3,
        },
        format="json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "position",
    [
        {"latitude": 0.0, "longitude": 0.0},
        {"latitude": 5e-8, "longitude": -5e-8},
        {"altitude": 10},
    ],
)
def test_ingest_null_island_or_missing_is_201_without_position(feeder, position):
    response = _ingest(feeder, position)
    assert response.status_code == 201, response.content
    packet = PositionPacket.objects.get(from_int=NODE)
    assert packet.latitude is None and packet.longitude is None
    assert Position.objects.count() == 0
    assert ObservedNode.objects.get(meshtastic_node_id=NODE).last_heard is not None


@pytest.mark.django_db
@pytest.mark.parametrize("lat,lon", [(51.5, -0.1), (0.0, 12.3), (12.3, 0.0), (2e-7, 0.0)])
def test_ingest_real_positions_are_kept(feeder, lat, lon):
    response = _ingest(feeder, {"latitude": lat, "longitude": lon})
    assert response.status_code == 201, response.content
    packet = PositionPacket.objects.get(from_int=NODE)
    assert (packet.latitude, packet.longitude) == (lat, lon)
    assert Position.objects.count() == 1
