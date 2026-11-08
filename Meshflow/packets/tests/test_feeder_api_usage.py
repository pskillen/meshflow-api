"""Feeder API usage fields and reported identity (ADR-0005), written by FeederApiUsageMixin."""

import logging
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.feeder_metrics import FEEDER_USAGE_WRITE_INTERVAL, record_feeder_usage
from common.protocol import Protocol
from nodes.admin import LegacyFeederUrlFilter, ManagedNodeAdmin
from nodes.models import ManagedNode, NodeAuth

FEEDER_NUM = 0x1A2B3C4D
NEW_NUM = 0x99887766
MC_PUBKEY = "ef" * 32


@pytest.fixture
def feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=FEEDER_NUM)
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


def _identity(api_key, **headers):
    return APIClient().get(reverse("feeder-v4-identity"), HTTP_X_API_KEY=api_key.key, **headers)


def _legacy_bot_version(node, api_key, url_name="meshtastic-bot-version", body=None, **headers):
    url = reverse(url_name, kwargs={"node_id": node.meshtastic_node_id})
    return APIClient().put(url, body or {"bot_version": "2.2.0"}, format="json", HTTP_X_API_KEY=api_key.key, **headers)


@pytest.mark.django_db
def test_v4_call_sets_generation_but_not_legacy(feeder):
    node, api_key = feeder

    assert _identity(api_key).status_code == 200

    node.refresh_from_db()
    assert node.feeder_api_generation == "v4"
    assert node.feeder_api_last_used_at is not None
    assert node.legacy_api_last_used_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,generation", [("meshtastic-bot-version", "v2"), ("meshtastic-bot-version-v3", "v3")])
def test_legacy_call_sets_legacy_last_used(feeder, url_name, generation):
    node, api_key = feeder

    assert _legacy_bot_version(node, api_key, url_name=url_name).status_code == 200

    node.refresh_from_db()
    assert node.feeder_api_generation == generation
    assert node.legacy_api_last_used_at is not None


@pytest.mark.django_db
def test_meshcore_prefix_call_sets_mc_prefix(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHCORE)
    node = create_managed_node(
        protocol=Protocol.MESHCORE, constellation=constellation, meshtastic_node_id=None, mc_pubkey=MC_PUBKEY
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    url = reverse("meshcore-feeder-bot-config", kwargs={"feeder_pubkey_prefix": MC_PUBKEY[:12]})
    response = APIClient().get(url, HTTP_X_API_KEY=api_key.key)

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.feeder_api_generation == "mc_prefix"
    assert node.legacy_api_last_used_at is not None


@pytest.mark.django_db
def test_reported_number_differs_is_accepted_and_flagged(feeder, caplog):
    node, api_key = feeder

    with caplog.at_level(logging.WARNING, logger="common.feeder_metrics"):
        response = APIClient().post(
            reverse("feeder-v4-meshtastic-ingest"),
            {
                "id": 777,
                "from": 0x0BADBEEF,
                "fromId": "!0badbeef",
                "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "after upgrade"},
                "rxTime": 1767225600,
            },
            format="json",
            HTTP_X_API_KEY=api_key.key,
            HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(NEW_NUM),
        )
    assert response.status_code == 201, response.content

    node.refresh_from_db()
    assert node.reported_meshtastic_node_id == NEW_NUM
    assert node.identity_reported_at is not None
    assert node.meshtastic_node_id == FEEDER_NUM  # never re-keyed here
    assert any("!99887766" in r.getMessage() and "!1a2b3c4d" in r.getMessage() for r in caplog.records)

    body = _identity(api_key).json()
    assert body["reported_meshtastic_node_id"] == NEW_NUM
    assert body["identity_mismatch"] is True


@pytest.mark.django_db
def test_identity_reflects_its_own_header(feeder):
    _node, api_key = feeder

    body = _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(NEW_NUM)).json()

    assert body["reported_meshtastic_node_id"] == NEW_NUM
    assert body["identity_mismatch"] is True


@pytest.mark.django_db
def test_matching_reported_number_is_not_a_mismatch(feeder):
    _node, api_key = feeder

    body = _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(FEEDER_NUM)).json()

    assert body["reported_meshtastic_node_id"] == FEEDER_NUM
    assert body["identity_mismatch"] is False


@pytest.mark.django_db
def test_legacy_url_records_reported_number(feeder):
    node, api_key = feeder

    response = _legacy_bot_version(node, api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(NEW_NUM))

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.reported_meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_bot_version_body_number_is_recorded(feeder):
    node, api_key = feeder

    response = APIClient().put(
        reverse("feeder-v4-bot-version"),
        {"bot_version": "2.3.0", "meshtastic_node_num": NEW_NUM},
        format="json",
        HTTP_X_API_KEY=api_key.key,
    )

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.reported_meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_invalid_header_is_ignored(feeder):
    node, api_key = feeder

    assert _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM="!1a2b3c4d").status_code == 200

    node.refresh_from_db()
    assert node.reported_meshtastic_node_id is None


@pytest.mark.django_db
def test_two_requests_within_ten_minutes_write_once(feeder):
    node, api_key = feeder

    with mock.patch("common.feeder_metrics.ManagedNode.objects.filter", wraps=ManagedNode.objects.filter) as spy:
        _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(NEW_NUM))
        first = ManagedNode.objects.get(pk=node.pk)
        _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(NEW_NUM))

    assert spy.call_count == 1  # one update() for two requests
    node.refresh_from_db()
    assert node.feeder_api_last_used_at == first.feeder_api_last_used_at
    assert node.identity_reported_at == first.identity_reported_at


@pytest.mark.django_db
def test_throttle_rules(feeder, django_assert_num_queries):
    node, _api_key = feeder
    now = timezone.now()

    with django_assert_num_queries(1):
        assert record_feeder_usage(node, api="v3", reported_node_num=NEW_NUM, now=now)
    with django_assert_num_queries(0):
        assert record_feeder_usage(node, api="v3", reported_node_num=NEW_NUM, now=now + timedelta(minutes=5)) == {}

    # A generation change writes at once.
    with django_assert_num_queries(1):
        written = record_feeder_usage(node, api="v4", reported_node_num=NEW_NUM, now=now + timedelta(minutes=6))
    assert set(written) == {"feeder_api_generation", "feeder_api_last_used_at"}

    # A changed reported number writes at once.
    written = record_feeder_usage(node, api="v4", reported_node_num=FEEDER_NUM, now=now + timedelta(minutes=7))
    assert set(written) == {"reported_meshtastic_node_id", "identity_reported_at"}

    # After the interval everything due is refreshed.
    later = now + timedelta(minutes=7) + FEEDER_USAGE_WRITE_INTERVAL
    written = record_feeder_usage(node, api="v4", reported_node_num=FEEDER_NUM, now=later)
    assert set(written) == {
        "feeder_api_generation",
        "feeder_api_last_used_at",
        "reported_meshtastic_node_id",
        "identity_reported_at",
    }

    node.refresh_from_db()
    assert node.feeder_api_last_used_at == later
    assert node.legacy_api_last_used_at == now


@pytest.mark.django_db
def test_admin_filter_lists_feeders_on_legacy_urls(feeder, create_managed_node):
    node, api_key = feeder
    stale = create_managed_node(meshtastic_node_id=FEEDER_NUM + 5, name="Stale")
    ManagedNode.objects.filter(pk=stale.pk).update(legacy_api_last_used_at=timezone.now() - timedelta(days=8))
    _legacy_bot_version(node, api_key)

    request = RequestFactory().get("/admin/nodes/managednode/", {"legacy_urls_7d": "yes"})
    model_admin = ManagedNodeAdmin(ManagedNode, AdminSite())
    flt = LegacyFeederUrlFilter(request, {"legacy_urls_7d": ["yes"]}, ManagedNode, model_admin)

    assert list(flt.queryset(request, ManagedNode.objects.all())) == [node]


FIRMWARE = "2.8.2.d5f1619"


@pytest.mark.django_db
def test_firmware_header_recorded_on_v4(feeder):
    node, api_key = feeder

    assert _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_FIRMWARE=FIRMWARE).status_code == 200

    node.refresh_from_db()
    assert node.reported_firmware_version == FIRMWARE
    assert node.firmware_reported_at is not None


@pytest.mark.django_db
def test_firmware_header_recorded_on_legacy_url(feeder):
    node, api_key = feeder

    assert _legacy_bot_version(node, api_key, HTTP_X_MESHTASTIC_FEEDER_FIRMWARE=FIRMWARE).status_code == 200

    node.refresh_from_db()
    assert node.reported_firmware_version == FIRMWARE


@pytest.mark.django_db
def test_firmware_body_recorded_and_header_wins(feeder):
    node, api_key = feeder
    url = reverse("feeder-v4-bot-version")
    body = {"bot_version": "2.3.0", "meshtastic_firmware_version": "2.7.26"}

    assert APIClient().put(url, body, format="json", HTTP_X_API_KEY=api_key.key).status_code == 200
    node.refresh_from_db()
    assert node.reported_firmware_version == "2.7.26"

    response = APIClient().put(
        url, body, format="json", HTTP_X_API_KEY=api_key.key, HTTP_X_MESHTASTIC_FEEDER_FIRMWARE=FIRMWARE
    )
    assert response.status_code == 200
    node.refresh_from_db()
    assert node.reported_firmware_version == FIRMWARE


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["", "   ", "2." * 40])
def test_blank_or_overlong_firmware_ignored(feeder, value):
    node, api_key = feeder

    assert _identity(api_key, HTTP_X_MESHTASTIC_FEEDER_FIRMWARE=value).status_code == 200

    node.refresh_from_db()
    assert node.reported_firmware_version is None
    assert node.firmware_reported_at is None


@pytest.mark.django_db
def test_firmware_throttle(feeder, django_assert_num_queries):
    node, _api_key = feeder
    now = timezone.now()

    record_feeder_usage(node, api="v4", reported_firmware=FIRMWARE, now=now)
    with django_assert_num_queries(0):
        assert record_feeder_usage(node, api="v4", reported_firmware=FIRMWARE, now=now + timedelta(minutes=5)) == {}

    written = record_feeder_usage(node, api="v4", reported_firmware="2.7.26", now=now + timedelta(minutes=6))
    assert written["reported_firmware_version"] == "2.7.26"

    written = record_feeder_usage(node, api="v4", reported_firmware="2.7.26", now=now + timedelta(minutes=20))
    assert "firmware_reported_at" in written


@pytest.mark.django_db
def test_meshcore_feeder_firmware_never_written(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHCORE)
    node = create_managed_node(
        protocol=Protocol.MESHCORE, constellation=constellation, meshtastic_node_id=None, mc_pubkey=MC_PUBKEY
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    url = reverse("meshcore-feeder-bot-config", kwargs={"feeder_pubkey_prefix": MC_PUBKEY[:12]})
    response = APIClient().get(url, HTTP_X_API_KEY=api_key.key, HTTP_X_MESHTASTIC_FEEDER_FIRMWARE=FIRMWARE)

    assert response.status_code == 200
    node.refresh_from_db()
    assert node.reported_firmware_version is None


@pytest.mark.django_db
def test_serializer_returns_firmware_fields(feeder):
    from nodes.serializers import ManagedNodeSerializer

    node, _api_key = feeder
    record_feeder_usage(node, api="v4", reported_firmware=FIRMWARE)

    data = ManagedNodeSerializer(node).data

    assert data["reported_firmware_version"] == FIRMWARE
    assert data["firmware_reported_at"] is not None
