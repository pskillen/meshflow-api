import pytest

from nodes.serializers import (
    APIKeyCreateSerializer,
    APIKeyDetailSerializer,
    APIKeyNodeSerializer,
    APIKeySerializer,
    PositionSerializer,
)


@pytest.mark.django_db
def test_api_key_serializer_valid_data(create_node_api_key):
    """Test API key serializer with valid data."""
    api_key = create_node_api_key()
    serializer = APIKeySerializer(api_key)
    data = serializer.data

    assert "id" in data
    assert "key" in data
    assert "name" in data
    assert "constellation" in data
    assert "created_at" in data
    assert "owner" in data
    assert "last_used" in data
    assert "is_active" in data


@pytest.mark.django_db
def test_api_key_node_serializer_valid_data(create_node_auth):
    """Test API key node serializer with valid data."""
    auth = create_node_auth()
    serializer = APIKeyNodeSerializer(auth)
    data = serializer.data

    assert "id" in data
    assert "api_key" in data
    assert "node" in data


@pytest.mark.django_db
def test_api_key_detail_serializer_valid_data(create_node_auth):
    """Test API key detail serializer with valid data."""
    auth = create_node_auth()
    serializer = APIKeyDetailSerializer(auth.api_key)
    data = serializer.data

    assert "id" in data
    assert "key" in data
    assert "name" in data
    assert "constellation" in data
    assert "created_at" in data
    assert "owner" in data
    assert "last_used" in data
    assert "is_active" in data
    assert "nodes" in data


@pytest.mark.django_db
def test_api_key_create_serializer_valid_data(create_user, create_constellation):
    """Test API key create serializer with valid data."""
    user = create_user()
    constellation = create_constellation(created_by=user)

    data = {"name": "Test API Key", "constellation": constellation.id, "nodes": []}

    serializer = APIKeyCreateSerializer(data=data, context={"request": type("Request", (), {"user": user})()})
    assert serializer.is_valid()
    api_key = serializer.save()

    assert api_key.name == "Test API Key"
    assert api_key.constellation == constellation
    assert api_key.owner == user


@pytest.mark.django_db
def test_position_serializer_valid_data(create_observed_node):
    """Test position serializer with valid data."""
    node = create_observed_node()
    position_data = {
        "node": node.internal_id,
        "logged_time": "2024-04-24T15:21:28.591639Z",
        "reported_time": "2024-04-24T15:21:28.591639Z",
        "latitude": 0.0,
        "longitude": 0.0,
        "altitude": 0,
        "heading": 0,
    }

    serializer = PositionSerializer(data=position_data)
    assert serializer.is_valid(), serializer.errors
    position = serializer.save()

    assert position.node == node
    assert position.latitude == 0.0
    assert position.longitude == 0.0
    assert position.altitude == 0
    assert position.heading == 0
    assert position.location_source == 0  # UNSET
