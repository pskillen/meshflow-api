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
