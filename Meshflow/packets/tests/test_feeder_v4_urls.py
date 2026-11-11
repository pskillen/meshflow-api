"""v4 feeder URLs (``/api/v4/feeder/``): key-scoped auth, no node number in the path."""

from unittest import mock

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.meshtastic_identity import normalise_pubkey
from common.protocol import Protocol
from nodes.models import NodeAuth, ObservedNode
from packets.models import MtRawPacket, PacketObservation

MC_PUBKEY = "cd" * 32
FEEDER_NUM = 0x1A2B3C4D
OBSERVED_NUM = 0x0BADBEEF


def _text_packet(packet_id=4242):
    return {
        "id": packet_id,
        "from": OBSERVED_NUM,
        "fromId": "!0badbeef",
        "to": 4294967295,
        "toId": "^all",
        "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello v4"},
        "rxTime": 1767225600,
    }


def _node_body():
    return {
        "id": OBSERVED_NUM,
        "long_name": "Observed by v4",
        "short_name": "OBV4",
    }


@pytest.fixture
def single_feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=FEEDER_NUM)
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


@pytest.fixture
def shared_key(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(constellation=constellation, name="A", meshtastic_node_id=FEEDER_NUM)
    node_b = create_managed_node(constellation=constellation, name="B", meshtastic_node_id=FEEDER_NUM + 1)
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)
    return node_a, api_key


@pytest.fixture
def meshcore_feeder(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHCORE)
    node = create_managed_node(
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        meshtastic_node_id=None,
        mc_pubkey=MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


def _call(name, api_key, method="post", data=None, **headers):
    client = APIClient()
    return getattr(client, method)(reverse(name), data, format="json", HTTP_X_API_KEY=api_key.key, **headers)


def test_v4_urls_resolve():
    assert reverse("feeder-v4-identity") == "/api/v4/feeder/identity/"
    assert reverse("feeder-v4-bot-version") == "/api/v4/feeder/bot-version/"
    assert reverse("feeder-v4-meshtastic-ingest") == "/api/v4/feeder/meshtastic/ingest/"
    assert reverse("feeder-v4-meshtastic-nodes") == "/api/v4/feeder/meshtastic/nodes/"


@pytest.mark.django_db
def test_identity_single_key(single_feeder):
    node, api_key = single_feeder

    response = _call("feeder-v4-identity", api_key, method="get")

    assert response.status_code == 200
    assert response.json() == {
        "internal_id": str(node.internal_id),
        "protocol": "meshtastic",
        "name": node.name,
        "constellation_id": node.constellation_id,
        "meshtastic_node_id": FEEDER_NUM,
        "node_id_str": "!1a2b3c4d",
        "reported_meshtastic_node_id": None,
        "identity_mismatch": False,
    }


@pytest.mark.django_db
def test_identity_meshcore_feeder(meshcore_feeder):
    node, api_key = meshcore_feeder

    response = _call("feeder-v4-identity", api_key, method="get")

    assert response.status_code == 200
    body = response.json()
    assert body["protocol"] == "meshcore"
    assert body["meshtastic_node_id"] is None
    assert body["identity_mismatch"] is False


@pytest.mark.django_db
def test_bot_version_single_key(single_feeder):
    node, api_key = single_feeder

    response = _call("feeder-v4-bot-version", api_key, method="put", data={"bot_version": "2.3.0"})

    assert response.status_code == 200
    assert response.data["bot_version"] == "2.3.0"
    node.refresh_from_db()
    assert node.bot_version == "2.3.0"


@pytest.mark.django_db
def test_bot_version_meshcore_feeder(meshcore_feeder):
    node, api_key = meshcore_feeder

    response = _call("feeder-v4-bot-version", api_key, method="post", data={"bot_version": "2.3.0"})

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.bot_version == "2.3.0"


@pytest.mark.django_db
def test_ingest_single_key(single_feeder):
    node, api_key = single_feeder

    response = _call("feeder-v4-meshtastic-ingest", api_key, data=_text_packet())

    assert response.status_code == 201, response.content
    assert response.data["status"] == "success"
    observation = PacketObservation.objects.get()
    assert observation.observer_id == node.pk


def _observation_fields():
    return sorted(
        (o.observer_id, o.packet.packet_id, o.packet.port_num, o.packet.from_int, o.packet.to_int, o.rx_time)
        for o in PacketObservation.objects.select_related("packet")
    )


@pytest.mark.django_db
def test_ingest_matches_v3_and_observer_is_keys_feeder(single_feeder):
    """v4 stores what v3 stores, attributed to the key's feeder (no node number in the URL)."""
    node, api_key = single_feeder
    client = APIClient()

    v3 = client.post(
        reverse("meshtastic-packet-ingest-v3", kwargs={"node_id": FEEDER_NUM}),
        _text_packet(),
        format="json",
        HTTP_X_API_KEY=api_key.key,
    )
    assert v3.status_code == 201, v3.content
    via_v3 = _observation_fields()
    PacketObservation.objects.all().delete()
    MtRawPacket.objects.all().delete()

    v4 = _call("feeder-v4-meshtastic-ingest", api_key, data=_text_packet())
    assert v4.status_code == 201, v4.content
    via_v4 = _observation_fields()

    assert via_v4 == via_v3
    assert {o[0] for o in via_v4} == {node.pk}


@pytest.fixture
def two_single_key_feeders(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(constellation=constellation, name="A", meshtastic_node_id=FEEDER_NUM)
    node_b = create_managed_node(constellation=constellation, name="B", meshtastic_node_id=FEEDER_NUM + 1)
    key_a = create_node_api_key(constellation=constellation)
    key_b = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=key_a, node=node_a)
    NodeAuth.objects.create(api_key=key_b, node=node_b)
    return node_a, node_b, key_a


@pytest.mark.django_db
def test_header_node_number_cannot_select_feeder_on_ingest(two_single_key_feeders):
    node_a, node_b, key_a = two_single_key_feeders

    response = _call(
        "feeder-v4-meshtastic-ingest",
        key_a,
        data=_text_packet(),
        HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(node_b.meshtastic_node_id),
    )

    assert response.status_code == 201, response.content
    assert set(PacketObservation.objects.values_list("observer_id", flat=True)) == {node_a.pk}
    node_a.refresh_from_db()
    node_b.refresh_from_db()
    assert node_a.meshtastic_node_id == FEEDER_NUM
    assert node_b.meshtastic_node_id == FEEDER_NUM + 1
    assert node_b.reported_meshtastic_node_id is None


@pytest.mark.django_db
def test_body_node_number_cannot_select_feeder_on_bot_version(two_single_key_feeders):
    node_a, node_b, key_a = two_single_key_feeders

    response = _call(
        "feeder-v4-bot-version",
        key_a,
        method="put",
        data={"bot_version": "9.9.9", "meshtastic_node_num": node_b.meshtastic_node_id},
    )

    assert response.status_code == 200, response.content
    node_a.refresh_from_db()
    node_b.refresh_from_db()
    assert node_a.bot_version == "9.9.9"
    assert node_b.bot_version != "9.9.9"
    assert node_a.meshtastic_node_id == FEEDER_NUM
    assert node_b.meshtastic_node_id == FEEDER_NUM + 1
    assert node_a.reported_meshtastic_node_id == FEEDER_NUM + 1
    assert node_b.reported_meshtastic_node_id is None


@pytest.mark.django_db
def test_node_upsert_without_path_number(single_feeder):
    node, api_key = single_feeder

    response = _call("feeder-v4-meshtastic-nodes", api_key, data=_node_body())

    assert response.status_code == 200, response.content
    assert ObservedNode.objects.filter(meshtastic_node_id=OBSERVED_NUM).exists()


@pytest.mark.django_db
def test_node_upsert_rejects_legacy_fields(single_feeder):
    """v4 nodes/ uses the strict v3 wire."""
    node, api_key = single_feeder
    body = _node_body()
    body["position"] = {"latitude": 51.5, "longitude": -0.12, "location_source": "LOC_INTERNAL"}

    response = _call("feeder-v4-meshtastic-nodes", api_key, data=body)

    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name,method,data",
    [
        ("feeder-v4-identity", "get", None),
        ("feeder-v4-bot-version", "put", {"bot_version": "2.3.0"}),
        ("feeder-v4-meshtastic-ingest", "post", _text_packet()),
        ("feeder-v4-meshtastic-nodes", "post", _node_body()),
    ],
)
def test_shared_key_is_403_with_code(shared_key, name, method, data):
    _node, api_key = shared_key

    response = _call(name, api_key, method=method, data=data)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "shared_api_key"
    assert "one API key per feeder" in body["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["feeder-v4-meshtastic-ingest", "feeder-v4-meshtastic-nodes"])
def test_meshcore_feeder_on_meshtastic_path(meshcore_feeder, name):
    _node, api_key = meshcore_feeder

    response = _call(name, api_key, data={})

    assert response.status_code == 403
    assert response.json()["code"] == "feeder_protocol_mismatch"


@pytest.mark.django_db
def test_unlinked_key_is_403_not_linked(create_node_api_key):
    api_key = create_node_api_key()

    response = _call("feeder-v4-identity", api_key, method="get")

    assert response.status_code == 403
    assert response.json()["code"] == "feeder_not_linked"


@pytest.mark.django_db
def test_bad_key_is_401():
    client = APIClient()

    response = client.get(reverse("feeder-v4-identity"), HTTP_X_API_KEY="not-a-key")

    assert response.status_code == 401


@pytest.mark.django_db
def test_missing_key_is_401():
    response = APIClient().get(reverse("feeder-v4-identity"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_legacy_urls_still_accept_shared_keys(shared_key):
    node, api_key = shared_key
    client = APIClient()

    for name in ("meshtastic-packet-ingest", "meshtastic-packet-ingest-v3"):
        url = reverse(name, kwargs={"node_id": node.meshtastic_node_id})
        response = client.post(url, _text_packet(), format="json", HTTP_X_API_KEY=api_key.key)
        assert response.status_code == 201, response.content

    url = reverse("meshtastic-node-upsert-v3", kwargs={"node_id": node.meshtastic_node_id})
    response = client.post(url, _node_body(), format="json", HTTP_X_API_KEY=api_key.key)
    assert response.status_code == 200

    url = reverse("meshtastic-bot-version", kwargs={"node_id": node.meshtastic_node_id})
    response = client.put(url, {"bot_version": "2.2.0"}, format="json", HTTP_X_API_KEY=api_key.key)
    assert response.status_code == 200


@pytest.mark.django_db
def test_legacy_node_upsert_still_checks_path_number(shared_key):
    node, api_key = shared_key
    client = APIClient()
    other = node.meshtastic_node_id + 1  # linked to the same key, but not the path's feeder

    url = reverse("meshtastic-node-upsert-v3", kwargs={"node_id": other})
    response = client.post(url, _node_body(), format="json", HTTP_X_API_KEY=api_key.key)
    assert response.status_code == 200

    url = reverse("meshtastic-node-upsert-v3", kwargs={"node_id": 999})
    response = client.post(url, _node_body(), format="json", HTTP_X_API_KEY=api_key.key)
    assert response.status_code == 403


# --- ID-4: automatic re-key on a reported number change --------------------------------------------------------

REKEY_OLD = 0xDA545C78
REKEY_NEW = 0x4396524C
REKEY_KEY_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="


@pytest.fixture
def rekey_feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(
        protocol=Protocol.MESHTASTIC,
        meshtastic_node_id=REKEY_OLD,
        meshtastic_public_key=normalise_pubkey(REKEY_KEY_B64),
    )
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


def _rekey_headers(num=REKEY_NEW, key=REKEY_KEY_B64):
    headers = {"HTTP_X_MESHTASTIC_FEEDER_NODE_NUM": str(num), "HTTP_X_MESHTASTIC_FEEDER_FIRMWARE": "2.8.2.d5f1619"}
    if key is not None:
        headers["HTTP_X_MESHTASTIC_FEEDER_PUBKEY"] = key
    return headers


@pytest.mark.django_db
def test_v4_ingest_applies_rekey(settings, rekey_feeder):
    from nodes.models import ManagedNodeIdentityEvent

    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    node, api_key = rekey_feeder

    response = _call("feeder-v4-meshtastic-ingest", api_key, data=_text_packet(), **_rekey_headers())

    assert response.status_code == 201, response.content
    node.refresh_from_db()
    assert node.meshtastic_node_id == REKEY_NEW
    assert node.reported_meshtastic_node_id == REKEY_NEW
    assert PacketObservation.objects.get().observer_id == node.pk
    assert ManagedNodeIdentityEvent.objects.get().outcome == ManagedNodeIdentityEvent.Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_v4_identity_endpoint_not_mismatched_on_applying_request(settings, rekey_feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _, api_key = rekey_feeder

    response = _call("feeder-v4-identity", api_key, method="get", **_rekey_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["meshtastic_node_id"] == REKEY_NEW
    assert body["identity_mismatch"] is False


@pytest.mark.django_db
def test_v4_flag_off_flags_and_keeps_number(settings, rekey_feeder):
    from nodes.models import ManagedNodeIdentityEvent

    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    node, api_key = rekey_feeder

    response = _call("feeder-v4-meshtastic-ingest", api_key, data=_text_packet(), **_rekey_headers())

    assert response.status_code == 201
    node.refresh_from_db()
    assert node.meshtastic_node_id == REKEY_OLD
    event = ManagedNodeIdentityEvent.objects.get()
    assert event.reason == ManagedNodeIdentityEvent.Reason.AUTO_REKEY_DISABLED


@pytest.mark.django_db
def test_v4_bot_version_body_pubkey(settings, rekey_feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    node, api_key = rekey_feeder

    response = _call(
        "feeder-v4-bot-version",
        api_key,
        data={
            "bot_version": "1.2.3",
            "meshtastic_node_num": REKEY_NEW,
            "meshtastic_public_key": REKEY_KEY_B64,
        },
    )

    assert response.status_code in (200, 201), response.content
    node.refresh_from_db()
    assert node.meshtastic_node_id == REKEY_NEW


@pytest.mark.django_db
def test_legacy_url_never_calls_rekey_service(settings, rekey_feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    node, api_key = rekey_feeder
    url = reverse("meshtastic-packet-ingest-v3", kwargs={"node_id": REKEY_OLD})

    with mock.patch("common.feeder_metrics.apply_reported_identity") as service:
        response = APIClient().post(url, _text_packet(), format="json", HTTP_X_API_KEY=api_key.key, **_rekey_headers())

    assert response.status_code == 201, response.content
    service.assert_not_called()
    node.refresh_from_db()
    assert node.meshtastic_node_id == REKEY_OLD


@pytest.mark.django_db
def test_service_exception_does_not_change_ingest(settings, rekey_feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _, api_key = rekey_feeder

    with mock.patch("common.feeder_metrics.apply_reported_identity", side_effect=RuntimeError("boom")):
        response = _call("feeder-v4-meshtastic-ingest", api_key, data=_text_packet(), **_rekey_headers())

    assert response.status_code == 201, response.content
    assert PacketObservation.objects.count() == 1


@pytest.mark.django_db
def test_bot_version_v4_stores_region_and_preset(single_feeder):
    node, api_key = single_feeder

    response = _call(
        "feeder-v4-bot-version",
        api_key,
        method="put",
        data={"bot_version": "2.4.0", "meshtastic_region": "3", "meshtastic_modem_preset": 9},
    )

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.meshtastic_region == "EU_868"
    assert node.meshtastic_modem_preset == "LONG_TURBO"


@pytest.mark.django_db
def test_bot_version_v4_meshcore_feeder_stores_no_radio_config(meshcore_feeder):
    node, api_key = meshcore_feeder

    response = _call(
        "feeder-v4-bot-version",
        api_key,
        method="post",
        data={"bot_version": "2.4.0", "meshtastic_region": "EU_868", "meshtastic_modem_preset": "LONG_FAST"},
    )

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.meshtastic_region is None
    assert node.meshtastic_modem_preset is None
    assert node.radio_config_reported_at is None
