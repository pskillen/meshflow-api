from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from nodes.models import NodeAuth


@pytest.mark.django_db
def test_bot_version_put_updates_managed_node(create_managed_node, create_node_api_key):
    managed_node = create_managed_node(meshtastic_node_id=42424242)
    api_key = create_node_api_key(owner=managed_node.owner, constellation=managed_node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=managed_node)

    client = APIClient()
    url = reverse("meshtastic-bot-version", kwargs={"node_id": managed_node.meshtastic_node_id})
    response = client.put(
        url,
        {"bot_version": "2.1.0"},
        format="json",
        HTTP_X_API_KEY=api_key.key,
    )

    assert response.status_code == 200
    assert response.data["bot_version"] == "2.1.0"
    managed_node.refresh_from_db()
    assert managed_node.bot_version == "2.1.0"
    assert managed_node.bot_version_reported_at is not None


@pytest.mark.django_db
def test_bot_version_denied_for_unlinked_node(create_managed_node, create_node_api_key):
    managed_node = create_managed_node(meshtastic_node_id=11111111)
    other_node = create_managed_node(meshtastic_node_id=22222222)
    api_key = create_node_api_key(owner=managed_node.owner, constellation=managed_node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=managed_node)

    client = APIClient()
    url = reverse("meshtastic-bot-version", kwargs={"node_id": other_node.meshtastic_node_id})
    response = client.put(
        url,
        {"bot_version": "2.1.0"},
        format="json",
        HTTP_X_API_KEY=api_key.key,
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_bot_version_blank_rejected(create_managed_node, create_node_api_key):
    managed_node = create_managed_node(meshtastic_node_id=33333333)
    api_key = create_node_api_key(owner=managed_node.owner, constellation=managed_node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=managed_node)

    client = APIClient()
    url = reverse("meshtastic-bot-version", kwargs={"node_id": managed_node.meshtastic_node_id})
    response = client.put(
        url,
        {"bot_version": "   "},
        format="json",
        HTTP_X_API_KEY=api_key.key,
    )

    assert response.status_code == 400


# --- LoRa region and modem preset -------------------------------------------------------------------------------


def _meshtastic_feeder(create_managed_node, create_node_api_key, node_id=51515151):
    managed_node = create_managed_node(meshtastic_node_id=node_id)
    api_key = create_node_api_key(owner=managed_node.owner, constellation=managed_node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=managed_node)
    return managed_node, api_key


def _report(managed_node, api_key, body, method="put"):
    url = reverse("meshtastic-bot-version", kwargs={"node_id": managed_node.meshtastic_node_id})
    return getattr(APIClient(), method)(url, body, format="json", HTTP_X_API_KEY=api_key.key)


@pytest.mark.django_db
def test_bot_version_stores_region_and_preset(create_managed_node, create_node_api_key):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)

    response = _report(
        managed_node,
        api_key,
        {"bot_version": "2.4.0", "meshtastic_region": "EU_868", "meshtastic_modem_preset": "LONG_FAST"},
    )

    assert response.status_code == 200
    managed_node.refresh_from_db()
    assert managed_node.meshtastic_region == "EU_868"
    assert managed_node.meshtastic_modem_preset == "LONG_FAST"
    assert managed_node.radio_config_reported_at is not None


@pytest.mark.django_db
def test_bot_version_preset_absent_means_custom(create_managed_node, create_node_api_key):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)
    managed_node.meshtastic_modem_preset = "LONG_FAST"
    managed_node.save()

    response = _report(managed_node, api_key, {"bot_version": "2.4.0", "meshtastic_region": "US"})

    assert response.status_code == 200
    managed_node.refresh_from_db()
    assert managed_node.meshtastic_region == "US"
    assert managed_node.meshtastic_modem_preset is None


@pytest.mark.django_db
def test_bot_version_without_region_leaves_radio_config(create_managed_node, create_node_api_key):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)
    _report(
        managed_node,
        api_key,
        {"bot_version": "2.4.0", "meshtastic_region": "EU_868", "meshtastic_modem_preset": "LONG_FAST"},
    )
    managed_node.refresh_from_db()
    reported_at = managed_node.radio_config_reported_at

    response = _report(managed_node, api_key, {"bot_version": "2.3.0"})

    assert response.status_code == 200
    managed_node.refresh_from_db()
    assert managed_node.meshtastic_region == "EU_868"
    assert managed_node.meshtastic_modem_preset == "LONG_FAST"
    assert managed_node.radio_config_reported_at == reported_at


@pytest.mark.django_db
def test_bot_version_unknown_numbers_normalised(create_managed_node, create_node_api_key):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)

    response = _report(
        managed_node,
        api_key,
        {"bot_version": "2.4.0", "meshtastic_region": "UNKNOWN_99", "meshtastic_modem_preset": "UNKNOWN_14"},
    )

    assert response.status_code == 200
    managed_node.refresh_from_db()
    assert managed_node.meshtastic_region == "REGION_99"
    assert managed_node.meshtastic_modem_preset == "TINY_FAST"


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["", "x" * 40, "bad\nvalue", 3.5, ["EU_868"], {"a": 1}, True])
def test_bot_version_garbage_radio_config_never_rejected(create_managed_node, create_node_api_key, bad):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)

    response = _report(
        managed_node,
        api_key,
        {"bot_version": "2.4.0", "meshtastic_region": bad, "meshtastic_modem_preset": bad},
    )

    assert response.status_code == 200
    managed_node.refresh_from_db()
    assert managed_node.bot_version == "2.4.0"
    assert managed_node.meshtastic_region is None
    assert managed_node.meshtastic_modem_preset is None


@pytest.mark.django_db
def test_managed_node_endpoint_returns_region_and_preset(create_managed_node, create_node_api_key):
    managed_node, api_key = _meshtastic_feeder(create_managed_node, create_node_api_key)
    _report(
        managed_node,
        api_key,
        {"bot_version": "2.4.0", "meshtastic_region": "EU_868", "meshtastic_modem_preset": "LONG_FAST"},
    )

    client = APIClient()
    client.force_authenticate(managed_node.owner)
    response = client.get(reverse("managed-nodes-detail", kwargs={"internal_id": managed_node.meshtastic_node_id}))

    assert response.status_code == 200, response.content
    assert response.data["meshtastic_region"] == "EU_868"
    assert response.data["meshtastic_modem_preset"] == "LONG_FAST"
    assert response.data["radio_config_reported_at"] is not None
