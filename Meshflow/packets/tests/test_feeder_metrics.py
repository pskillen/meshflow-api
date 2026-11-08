"""Prometheus counters for feeder API usage (one request per API generation)."""

from django.urls import reverse

import pytest
from prometheus_client import REGISTRY
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import NodeAuth

FEEDER_NUM = 0x1A2B3C4D
MC_PUBKEY = "a1" * 32


def _requests(**labels):
    return REGISTRY.get_sample_value("meshflow_feeder_api_requests_total", labels) or 0.0


def _rejections(**labels):
    return REGISTRY.get_sample_value("meshflow_feeder_auth_rejections_total", labels) or 0.0


@pytest.fixture
def feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=FEEDER_NUM)
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name,api",
    [("meshtastic-bot-version", "v2"), ("meshtastic-bot-version-v3", "v3")],
)
def test_legacy_meshtastic_request_counted(feeder, url_name, api):
    node, api_key = feeder
    labels = {"api": api, "protocol": "meshtastic", "endpoint": "bot-version", "status_class": "2xx"}
    before = _requests(**labels)

    url = reverse(url_name, kwargs={"node_id": node.meshtastic_node_id})
    response = APIClient().put(url, {"bot_version": "2.2.0"}, format="json", HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 200
    assert _requests(**labels) == before + 1


@pytest.mark.django_db
def test_v4_request_counted(feeder):
    _node, api_key = feeder
    labels = {"api": "v4", "protocol": "meshtastic", "endpoint": "identity", "status_class": "2xx"}
    before = _requests(**labels)

    response = APIClient().get(reverse("feeder-v4-identity"), HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 200
    assert _requests(**labels) == before + 1


@pytest.mark.django_db
def test_mc_prefix_request_counted(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHCORE)
    node = create_managed_node(
        protocol=Protocol.MESHCORE, constellation=constellation, meshtastic_node_id=None, mc_pubkey=MC_PUBKEY
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    labels = {"api": "mc_prefix", "protocol": "meshcore", "endpoint": "bot-config", "status_class": "2xx"}
    before = _requests(**labels)

    url = reverse("meshcore-feeder-bot-config", kwargs={"feeder_pubkey_prefix": MC_PUBKEY[:12]})
    response = APIClient().get(url, HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 200
    assert _requests(**labels) == before + 1


@pytest.mark.django_db
def test_v4_rejection_counted_by_code(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(constellation=constellation, name="A", meshtastic_node_id=FEEDER_NUM)
    node_b = create_managed_node(constellation=constellation, name="B", meshtastic_node_id=FEEDER_NUM + 1)
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)
    rejected = {"api": "v4", "code": "shared_api_key"}
    counted = {"api": "v4", "protocol": "meshtastic", "endpoint": "ingest", "status_class": "4xx"}
    before_rejected, before_counted = _rejections(**rejected), _requests(**counted)

    response = APIClient().post(reverse("feeder-v4-meshtastic-ingest"), {}, format="json", HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 403
    assert _rejections(**rejected) == before_rejected + 1
    assert _requests(**counted) == before_counted + 1


@pytest.mark.django_db
def test_legacy_rejection_counted_as_not_linked(feeder):
    _node, api_key = feeder
    rejected = {"api": "v3", "code": "not_linked"}
    before = _rejections(**rejected)

    url = reverse("meshtastic-packet-ingest-v3", kwargs={"node_id": 999})
    response = APIClient().post(url, {}, format="json", HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 403
    assert _rejections(**rejected) == before + 1
