"""2.8 connect-time replay: stored, flagged on the observation, and nothing else changes.

Request bodies are the ``packet`` dicts of ``spare_2.8_hop4_capture.jsonl`` (lines 3 and 42 replay, 83 live), with
``raw`` keys dropped and coordinates rounded to one decimal place (fixture scrub rule).
"""

from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import DeviceMetrics, NodeAuth, NodeLatestStatus, ObservedNode, Position
from packets.models import DeviceMetricsPacket, GenericPacket, PacketObservation, PositionPacket
from packets.serializers import PrefetchedPacketObservationSerializer

FEEDER_OLD_NUM = 0x1A83CF89
FEEDER_NEW_NUM = 3769067321  # !e0a76739, in the header only
SENDER = 52741281  # !0324c4a1
STABLE_ID = 3909798862
ALL = 4294967295


def replayed_position(**overrides):
    body = {
        "from": SENDER,
        "to": ALL,
        "decoded": {
            "portnum": "POSITION_APP",
            "position": {
                "latitudeI": 560000000,
                "longitudeI": -36000000,
                "altitude": 53,
                "time": 1755077015,
                "locationSource": "LOC_MANUAL",
                "precisionBits": 32,
                "latitude": 56.0,
                "longitude": -3.6,
            },
        },
        "id": 3442272654,
        "rxTime": 1755078058,
        "rxSnr": 6.25,
        "priority": "BACKGROUND",
        "hopStart": 4,
        "transportMechanism": "TRANSPORT_LORA",
        "fromId": "!0324c4a1",
        "toId": "^all",
    }
    body.update(overrides)
    return body


def replayed_device_metrics(**overrides):
    body = {
        "from": SENDER,
        "to": ALL,
        "decoded": {
            "portnum": "TELEMETRY_APP",
            "telemetry": {
                "time": 1755078058,
                "deviceMetrics": {
                    "batteryLevel": 47,
                    "voltage": 3.699,
                    "channelUtilization": 2.3533332,
                    "airUtilTx": 0.060222223,
                    "uptimeSeconds": 56890,
                },
            },
        },
        "id": 3442272653,
        "rxTime": 1755078058,
        "rxSnr": 6.25,
        "priority": "BACKGROUND",
        "hopStart": 4,
        "transportMechanism": "TRANSPORT_LORA",
        "fromId": "!0324c4a1",
        "toId": "^all",
    }
    body.update(overrides)
    return body


def replayed_node_status(**overrides):
    body = {
        "from": SENDER,
        "to": ALL,
        "decoded": {"portnum": 36, "payload": "CAE="},
        "id": 3442272655,
        "rxTime": 1755078058,
        "priority": "BACKGROUND",
        "hopStart": 3,
        "hopLimit": 3,
        "transportMechanism": "TRANSPORT_LORA",
    }
    body.update(overrides)
    return body


def live_position(**overrides):
    body = replayed_position(
        id=1126200599,
        rxTime=int(timezone.now().timestamp()),
        rxRssi=-81,
        hopStart=7,
        hopLimit=5,
        relayNode=240,
    )
    del body["priority"]
    body.update(overrides)
    return body


@pytest.fixture
def feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=FEEDER_OLD_NUM)
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


@pytest.fixture
def post_v4(feeder):
    _, api_key = feeder

    def _post(body, api_key_override=None, header=FEEDER_NEW_NUM):
        extra = {"HTTP_X_MESHTASTIC_FEEDER_NODE_NUM": str(header)} if header else {}
        return APIClient().post(
            reverse("feeder-v4-meshtastic-ingest"),
            body,
            format="json",
            HTTP_X_API_KEY=(api_key_override or api_key).key,
            **extra,
        )

    return _post


@pytest.fixture
def post_v3(feeder):
    node, api_key = feeder

    def _post(body):
        url = reverse("meshtastic-packet-ingest-v3", kwargs={"node_id": node.meshtastic_node_id})
        return APIClient().post(url, body, format="json", HTTP_X_API_KEY=api_key.key)

    return _post


@pytest.fixture(params=["v4", "v3"])
def post(request, post_v4, post_v3):
    return post_v4 if request.param == "v4" else post_v3


@pytest.fixture
def guards(settings):
    """Patch every side-effect entry point a processed packet could reach."""
    settings.DX_MONITORING_DETECTION_ENABLED = True
    with (
        patch("dx_monitoring.services.maybe_detect_dx_candidate") as dx,
        patch("packets.receivers.enqueue_new_node_baseline") as baseline_a,
        patch("traceroute.receivers.enqueue_new_node_baseline") as baseline_b,
    ):
        yield {"dx": dx, "baseline_a": baseline_a, "baseline_b": baseline_b}


def assert_nothing_driven(guards):
    guards["dx"].assert_not_called()
    guards["baseline_a"].assert_not_called()
    guards["baseline_b"].assert_not_called()
    assert ObservedNode.objects.count() == 0
    assert Position.objects.count() == 0
    assert DeviceMetrics.objects.count() == 0
    assert NodeLatestStatus.objects.count() == 0


@pytest.mark.django_db
def test_replayed_position_is_stored_flagged_and_drives_nothing(post, guards):
    response = post(replayed_position())

    assert response.status_code == 201, response.content
    assert response.json() == {"status": "success", "message": "Packet ingested successfully"}
    assert PositionPacket.objects.count() == 1
    observation = PacketObservation.objects.get()
    assert observation.replayed is True
    assert_nothing_driven(guards)


@pytest.mark.django_db
def test_replayed_device_metrics_is_stored_flagged_and_drives_nothing(post, guards):
    response = post(replayed_device_metrics())

    assert response.status_code == 201, response.content
    assert DeviceMetricsPacket.objects.count() == 1
    assert PacketObservation.objects.get().replayed is True
    assert_nothing_driven(guards)


@pytest.mark.django_db
def test_replay_does_not_move_an_existing_node(post, guards, create_observed_node):
    long_ago = timezone.now() - timedelta(days=3)
    node = create_observed_node(meshtastic_node_id=SENDER)
    ObservedNode.objects.filter(pk=node.pk).update(last_heard=long_ago)
    NodeLatestStatus.objects.create(node=node, meshtastic_inferred_max_hops=2)

    for body in (replayed_position(), replayed_device_metrics()):
        assert post(body).status_code == 201

    node.refresh_from_db()
    assert node.last_heard == long_ago
    status = NodeLatestStatus.objects.get(node=node)
    assert status.meshtastic_inferred_max_hops == 2
    assert status.meshtastic_inferred_max_hops_at is None
    assert status.latitude is None
    assert status.battery_level is None
    assert Position.objects.count() == 0
    assert DeviceMetrics.objects.count() == 0
    guards["dx"].assert_not_called()
    guards["baseline_a"].assert_not_called()
    guards["baseline_b"].assert_not_called()


@pytest.mark.django_db
def test_replayed_node_status_leaves_inferred_max_hops(post, guards, create_observed_node):
    node = create_observed_node(meshtastic_node_id=SENDER)
    NodeLatestStatus.objects.create(node=node, meshtastic_inferred_max_hops=5)

    response = post(replayed_node_status())

    assert response.status_code == 201, response.content
    assert GenericPacket.objects.count() == 1
    assert PacketObservation.objects.get().replayed is True
    assert NodeLatestStatus.objects.get(node=node).meshtastic_inferred_max_hops == 5


@pytest.mark.django_db
def test_posting_again_adds_no_rows(post, guards):
    assert post(replayed_position()).status_code == 201
    assert post(replayed_position()).status_code == 201
    # The same record after a reconnect: hopStart and hopLimit change, the id does not.
    assert post(replayed_position(hopStart=4, hopLimit=1, rxTime=1755078090)).status_code == 201

    assert PositionPacket.objects.count() == 1
    assert PacketObservation.objects.count() == 1


@pytest.mark.django_db
def test_stable_id_with_changed_hop_fields_is_one_observation(post, guards):
    first = replayed_position(id=STABLE_ID, hopStart=3, hopLimit=3)
    second = replayed_position(id=STABLE_ID, hopStart=4, hopLimit=4)

    assert post(first).status_code == 201
    assert post(second).status_code == 201

    assert PositionPacket.objects.count() == 1
    observation = PacketObservation.objects.get()
    assert (observation.hop_start, observation.hop_limit) == (3, 3)  # first wins


@pytest.mark.django_db
def test_stable_id_from_a_second_feeder_is_a_second_observation(
    post_v4, guards, create_managed_node, create_node_api_key, feeder
):
    other = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=0x2B94D09A)
    other_key = create_node_api_key(owner=other.owner, constellation=other.constellation)
    NodeAuth.objects.create(api_key=other_key, node=other)

    assert post_v4(replayed_position(id=STABLE_ID, hopStart=3, hopLimit=3)).status_code == 201
    assert (
        post_v4(replayed_position(id=STABLE_ID, hopStart=4, hopLimit=4), other_key, header=0x2B94D09A).status_code
        == 201
    )

    assert PositionPacket.objects.count() == 1
    assert PacketObservation.objects.count() == 2
    assert set(PacketObservation.objects.values_list("replayed", flat=True)) == {True}


@pytest.mark.django_db
def test_live_packet_with_rssi_is_processed_as_today(post_v4, guards):
    with patch("packets.receivers.enqueue_new_node_baseline"):
        response = post_v4(live_position())

    assert response.status_code == 201, response.content
    assert PacketObservation.objects.get().replayed is False
    assert ObservedNode.objects.filter(meshtastic_node_id=SENDER).exists()
    assert Position.objects.count() == 1


@pytest.mark.django_db
def test_self_telemetry_is_not_replayed(post_v4, guards):
    body = replayed_device_metrics(**{"from": FEEDER_NEW_NUM, "fromId": "!e0a76739"})
    del body["transportMechanism"]

    assert post_v4(body).status_code == 201

    assert PacketObservation.objects.get().replayed is False


@pytest.mark.django_db
def test_own_packet_with_replay_shape_is_not_replayed(post_v4, guards):
    body = replayed_device_metrics(**{"from": FEEDER_NEW_NUM, "fromId": "!e0a76739"})

    assert post_v4(body).status_code == 201

    assert PacketObservation.objects.get().replayed is False


@pytest.mark.django_db
def test_mqtt_shaped_live_packet_is_not_replayed(post_v4, guards):
    body = live_position(transportMechanism="TRANSPORT_MQTT")
    del body["rxRssi"]

    assert post_v4(body).status_code == 201

    assert PacketObservation.objects.get().replayed is False
    assert Position.objects.count() == 1


@pytest.mark.django_db
def test_body_flag_marks_a_live_shaped_packet(post, guards):
    body = live_position(replayed=True)

    assert post(body).status_code == 201

    assert PacketObservation.objects.get().replayed is True
    assert_nothing_driven(guards)


@pytest.mark.django_db
def test_kill_switch_off_ignores_shape_but_honours_flag(post_v4, guards, settings):
    settings.MESHTASTIC_REPLAY_SHAPE_DETECTION = False
    with patch("packets.receivers.enqueue_new_node_baseline"):
        assert post_v4(replayed_position()).status_code == 201
        assert PacketObservation.objects.get().replayed is False

        PacketObservation.objects.all().delete()
        assert post_v4(replayed_device_metrics(replayed=True)).status_code == 201
        assert PacketObservation.objects.get().replayed is True


@pytest.mark.django_db
def test_flag_never_flips_an_existing_observation(post_v4, guards):
    body = live_position()
    with patch("packets.receivers.enqueue_new_node_baseline"):
        assert post_v4(body).status_code == 201
        assert post_v4({**body, "replayed": True}).status_code == 201

    assert PacketObservation.objects.count() == 1
    assert PacketObservation.objects.get().replayed is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "hop_start,hop_limit,bitfield",
    [(3, 3, None), (3, 3, 1), (4, 4, 0)],
)
def test_observation_api_reports_no_hops_for_a_replay(create_packet_observation, hop_start, hop_limit, bitfield):
    observation = create_packet_observation(hop_start=hop_start, hop_limit=hop_limit, bitfield=bitfield, replayed=True)

    data = PrefetchedPacketObservationSerializer(observation, context={}).data

    assert data["replayed"] is True
    assert data["hop_count"] is None
    assert data["direct_from_sender"] is False


@pytest.mark.django_db
def test_observation_api_live_observation_is_unchanged(create_packet_observation):
    observation = create_packet_observation(hop_start=3, hop_limit=3)

    data = PrefetchedPacketObservationSerializer(observation, context={}).data

    assert data["replayed"] is False
    assert data["hop_count"] == 0
    assert data["direct_from_sender"] is True
