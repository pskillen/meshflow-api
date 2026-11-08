"""v4 feeder URLs (``/api/v4/feeder/``): key-scoped auth, no node number in the path."""

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import NodeAuth, ObservedNode

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
