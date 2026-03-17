from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.mesh_node_helpers import meshtastic_id_to_hex


@pytest.mark.django_db
def test_managed_node_list_view(create_managed_node, create_user):
    """Test managed node list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test nodes
    node1 = create_managed_node(owner=user)  # noqa: F841
    node2 = create_managed_node(owner=user)  # noqa: F841

    # Test GET request
    response = client.get(reverse("managed-nodes-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_managed_node_detail_view(create_managed_node, create_user):
    """Test managed node detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test node
    node = create_managed_node(owner=user)

    # Test GET request
    response = client.get(reverse("managed-nodes-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["node_id"] == node.node_id


@pytest.mark.django_db
def test_observed_node_list_view(create_observed_node, create_user):
    """Test observed node list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test nodes
    node1 = create_observed_node()  # noqa: F841
    node2 = create_observed_node()  # noqa: F841

    # Test GET request
    response = client.get(reverse("observed-node-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_observed_node_detail_view(create_observed_node, create_user):
    """Test observed node detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test node
    node = create_observed_node()

    # Test GET request
    response = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["node_id"] == node.node_id


@pytest.mark.django_db
def test_node_api_key_list_view(create_node_api_key, create_user):
    """Test node API key list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test API keys
    key1 = create_node_api_key(owner=user)  # noqa: F841
    key2 = create_node_api_key(owner=user)  # noqa: F841

    # Test GET request
    response = client.get(reverse("api-keys-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_node_api_key_detail_view(create_node_api_key, create_user):
    """Test node API key detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test API key
    api_key = create_node_api_key(owner=user)

    # Test GET request
    response = client.get(reverse("api-keys-detail", kwargs={"pk": api_key.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(api_key.id)


@pytest.mark.django_db
def test_claim_post_rejected_when_node_owned_by_another_user(create_observed_node, create_user):
    """POST to create claim returns 400 when node is already claimed by another user."""
    owner = create_user()
    other_user = create_user()
    node_id = 111222333444
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=owner,
    )

    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.post(
        reverse("observed-node-claim", kwargs={"node_id": node.node_id}),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already claimed" in response.data["detail"].lower()
