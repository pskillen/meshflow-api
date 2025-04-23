import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from nodes.models import ManagedNode, ObservedNode, NodeAPIKey, NodeAuth


@pytest.mark.django_db
def test_managed_node_list_view(create_managed_node, create_user):
    """Test managed node list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    
    # Create some test nodes
    node1 = create_managed_node(owner=user)
    node2 = create_managed_node(owner=user)
    
    # Test GET request
    response = client.get(reverse('managed-node-list'))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2


@pytest.mark.django_db
def test_managed_node_detail_view(create_managed_node, create_user):
    """Test managed node detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    
    # Create a test node
    node = create_managed_node(owner=user)
    
    # Test GET request
    response = client.get(reverse('managed-node-detail', args=[node.node_id]))
    assert response.status_code == status.HTTP_200_OK
    assert response.data['node_id'] == node.node_id


@pytest.mark.django_db
def test_observed_node_list_view(create_observed_node):
    """Test observed node list view."""
    client = APIClient()
    
    # Create some test nodes
    node1 = create_observed_node()
    node2 = create_observed_node()
    
    # Test GET request
    response = client.get(reverse('observed-node-list'))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2


@pytest.mark.django_db
def test_observed_node_detail_view(create_observed_node):
    """Test observed node detail view."""
    client = APIClient()
    
    # Create a test node
    node = create_observed_node()
    
    # Test GET request
    response = client.get(reverse('observed-node-detail', args=[node.node_id]))
    assert response.status_code == status.HTTP_200_OK
    assert response.data['node_id'] == node.node_id


@pytest.mark.django_db
def test_node_api_key_list_view(create_node_api_key, create_user):
    """Test node API key list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    
    # Create some test API keys
    key1 = create_node_api_key(created_by=user)
    key2 = create_node_api_key(created_by=user)
    
    # Test GET request
    response = client.get(reverse('node-api-key-list'))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2


@pytest.mark.django_db
def test_node_api_key_detail_view(create_node_api_key, create_user):
    """Test node API key detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    
    # Create a test API key
    api_key = create_node_api_key(created_by=user)
    
    # Test GET request
    response = client.get(reverse('node-api-key-detail', args=[api_key.id]))
    assert response.status_code == status.HTTP_200_OK
    assert response.data['id'] == api_key.id 