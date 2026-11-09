"""Unknown ports, unknown telemetry variants and a missing rxTime are stored, never a 400 (#461, #479, #462)."""

from datetime import datetime, timezone

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from nodes.models import ObservedNode
from packets.models import DeviceMetricsPacket, GenericPacket, LocalStatsPacket, MtRawPacket, PacketObservation
from packets.serializers import PacketIngestSerializer

NODE = 0x1A2B3C4D
RX = 1672531200
RX_DT = datetime(2023, 1, 1, tzinfo=timezone.utc)


def _client_for(auth):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=auth.api_key.key)
    return {"client": client, "node": auth.node}


@pytest.fixture
def feeder(create_node_auth):
    return _client_for(create_node_auth())


def _ingest(feeder, payload):
    url = reverse("meshtastic-packet-ingest", kwargs={"node_id": feeder["node"].meshtastic_node_id})
    return feeder["client"].post(url, payload, format="json")


def _payload(portnum, packet_id=5001, decoded=None, **extra):
    body = {
        "id": packet_id,
        "from": NODE,
        "to": 0xFFFFFFFF,
        "decoded": {"portnum": portnum, **(decoded or {})},
        "rxTime": RX,
    }
    body.update(extra)
    return body


PORT_CASES = [
    ("STORE_FORWARD_APP", "STORE_FORWARD_APP"),
    (38, "PAGING_APP"),
    ("38", "PAGING_APP"),
    (37, "MESH_BEACON_APP"),
    (79, "LORA_OTA_APP"),
    ("PORT_999", "PORT_999"),
    (999, "PORT_999"),
    ("ROUTING_APP", "ROUTING_APP"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("portnum,expected", PORT_CASES)
def test_unknown_port_is_stored(feeder, portnum, expected):
    resp = _ingest(feeder, _payload(portnum, decoded={"storeAndForward": {"rr": "ROUTER_HEARTBEAT"}}))
    assert resp.status_code == 201, resp.content

    packet = GenericPacket.objects.get()
    assert packet.port_num == expected
    assert packet.telemetry_variant is None
    assert PacketObservation.objects.filter(packet=packet).count() == 1
    node = ObservedNode.objects.get(meshtastic_node_id=NODE)
    assert node.last_heard == RX_DT


@pytest.mark.django_db
def test_decoded_is_stored_without_portnum(feeder):
    decoded = {"storeAndForward": {"rr": "ROUTER_HEARTBEAT"}}
    assert _ingest(feeder, _payload("STORE_FORWARD_APP", decoded=decoded)).status_code == 201
    packet = GenericPacket.objects.get()
    assert packet.decoded == decoded
    assert not packet.decoded_truncated


@pytest.mark.django_db
def test_routing_app_is_metadata_only(feeder):
    resp = _ingest(feeder, _payload("ROUTING_APP", decoded={"routing": {"errorReason": "NONE"}}))
    assert resp.status_code == 201
    packet = GenericPacket.objects.get()
    assert packet.decoded is None
    assert not packet.decoded_truncated


@pytest.mark.django_db
def test_metadata_only_ports_are_configurable(feeder, settings):
    settings.MESHTASTIC_METADATA_ONLY_PORTNUMS = ["ROUTING_APP", "STORE_FORWARD_APP"]
    assert _ingest(feeder, _payload("STORE_FORWARD_APP", decoded={"x": {"a": 1}})).status_code == 201
    assert GenericPacket.objects.get().decoded is None


@pytest.mark.django_db
def test_large_payload_is_truncated(feeder):
    decoded = {"storeAndForward": {"blob": "x" * 5000}}
    assert _ingest(feeder, _payload("STORE_FORWARD_APP", decoded=decoded)).status_code == 201
    packet = GenericPacket.objects.get()
    assert packet.decoded is None
    assert packet.decoded_truncated is True


@pytest.mark.django_db
def test_payload_cap_is_configurable(feeder, settings):
    settings.MESHTASTIC_GENERIC_DECODED_MAX_BYTES = 10
    assert _ingest(feeder, _payload("STORE_FORWARD_APP", decoded={"a": {"b": "0123456789"}})).status_code == 201
    packet = GenericPacket.objects.get()
    assert packet.decoded is None and packet.decoded_truncated is True


@pytest.mark.django_db
def test_unknown_telemetry_variant_is_stored(feeder):
    decoded = {"telemetry": {"time": 1, "soilWaterMetrics": {"moisture": 4}}}
    resp = _ingest(feeder, _payload("TELEMETRY_APP", decoded=decoded))
    assert resp.status_code == 201, resp.content
    packet = GenericPacket.objects.get()
    assert packet.port_num == "TELEMETRY_APP"
    assert packet.telemetry_variant == "soilWaterMetrics"
    assert packet.decoded == decoded
    assert PacketObservation.objects.filter(packet=packet).count() == 1
    assert ObservedNode.objects.get(meshtastic_node_id=NODE).last_heard == RX_DT


@pytest.mark.django_db
def test_telemetry_without_any_variant_is_stored_without_variant(feeder):
    resp = _ingest(feeder, _payload("TELEMETRY_APP", decoded={"telemetry": {"time": 1}}))
    assert resp.status_code == 201
    assert GenericPacket.objects.get().telemetry_variant is None


@pytest.mark.django_db
def test_known_telemetry_variant_still_goes_to_typed_table(feeder):
    decoded = {"telemetry": {"time": 1, "deviceMetrics": {"batteryLevel": 50}}}
    assert _ingest(feeder, _payload("TELEMETRY_APP", decoded=decoded)).status_code == 201
    assert DeviceMetricsPacket.objects.count() == 1
    assert GenericPacket.objects.count() == 0


@pytest.mark.django_db
def test_typed_port_sent_as_int_goes_to_typed_table(feeder):
    assert _ingest(feeder, _payload(1, decoded={"text": "hi"})).status_code == 201
    assert MtRawPacket.objects.get().port_num == "TEXT_MESSAGE_APP"
    assert GenericPacket.objects.count() == 0


@pytest.mark.django_db
def test_missing_portnum_or_decoded_is_400(feeder):
    payload = _payload("STORE_FORWARD_APP")
    del payload["decoded"]["portnum"]
    assert _ingest(feeder, payload).status_code == 400
    payload = _payload("STORE_FORWARD_APP")
    del payload["decoded"]
    assert _ingest(feeder, payload).status_code == 400
    assert MtRawPacket.objects.count() == 0


@pytest.mark.django_db
def test_overlong_portnum_is_400(feeder):
    assert _ingest(feeder, _payload("X" * 60)).status_code == 400


@pytest.mark.django_db
def test_two_feeders_one_packet_two_observations(feeder, create_node_auth):
    second = _client_for(create_node_auth())
    payload = _payload("STORE_FORWARD_APP", decoded={"storeAndForward": {"rr": "ROUTER_HEARTBEAT"}})
    assert _ingest(feeder, payload).status_code == 201
    assert _ingest(second, payload).status_code == 201
    assert GenericPacket.objects.count() == 1
    assert PacketObservation.objects.count() == 2


# --- missing rxTime -------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("rx", ["absent", None, 0])
def test_missing_rx_time_is_estimated(feeder, rx):
    payload = _payload("STORE_FORWARD_APP", decoded={"storeAndForward": {}})
    if rx == "absent":
        del payload["rxTime"]
    else:
        payload["rxTime"] = rx
    assert _ingest(feeder, payload).status_code == 201
    obs = PacketObservation.objects.get()
    assert obs.rx_time_estimated is True
    assert obs.rx_time.year >= 2026


@pytest.mark.django_db
def test_supplied_rx_time_is_not_estimated(feeder):
    assert _ingest(feeder, _payload("STORE_FORWARD_APP", decoded={"a": {}})).status_code == 201
    obs = PacketObservation.objects.get()
    assert obs.rx_time_estimated is False
    assert obs.rx_time == RX_DT


@pytest.mark.django_db
def test_telemetry_without_time_or_rx_time_falls_back_to_estimated_time(feeder):
    payload = _payload("TELEMETRY_APP", decoded={"telemetry": {"deviceMetrics": {"batteryLevel": 50}}})
    del payload["rxTime"]
    assert _ingest(feeder, payload).status_code == 201
    obs = PacketObservation.objects.get()
    packet = DeviceMetricsPacket.objects.get()
    assert obs.rx_time_estimated is True
    assert packet.reading_time == obs.rx_time


@pytest.mark.django_db
def test_serializer_flags_estimate(create_node_auth):
    auth = create_node_auth()
    data = _payload("STORE_FORWARD_APP", decoded={"a": {}})
    del data["rxTime"]
    serializer = PacketIngestSerializer(data=data, context={"observer": auth.node})
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert serializer.observation.rx_time_estimated is True


# --- last_heard for stats packets ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_local_stats_advances_last_heard(feeder):
    decoded = {"telemetry": {"time": 1, "localStats": {"numPacketsTx": 3, "numPacketsRx": 4}}}
    assert _ingest(feeder, _payload("TELEMETRY_APP", decoded=decoded)).status_code == 201
    assert LocalStatsPacket.objects.count() == 1
    assert ObservedNode.objects.get(meshtastic_node_id=NODE).last_heard is not None


@pytest.mark.django_db
def test_traffic_management_stats_advances_last_heard(feeder):
    decoded = {"telemetry": {"time": 1, "trafficManagementStats": {"packetsInspected": 3}}}
    assert _ingest(feeder, _payload("TELEMETRY_APP", decoded=decoded)).status_code == 201
    assert ObservedNode.objects.get(meshtastic_node_id=NODE).last_heard is not None
