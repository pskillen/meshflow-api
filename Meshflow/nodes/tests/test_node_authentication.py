import pytest

from nodes.authentication import NodeAPIKeyAuthentication


@pytest.mark.django_db
def test_node_api_key_authentication_valid_key(create_node_api_key):
    """Test node API key authentication with valid key."""
    api_key = create_node_api_key()
    auth = NodeAPIKeyAuthentication()

    # Test authentication
    request = type("Request", (), {"META": {"HTTP_X_API_KEY": api_key.key}})()
    user, auth_key = auth.authenticate(request)

    assert user == api_key.constellation
    assert auth_key == api_key


@pytest.mark.django_db
def test_node_api_key_authentication_invalid_key():
    """Test node API key authentication with invalid key."""
    auth = NodeAPIKeyAuthentication()

    # Test with invalid key
    request = type("Request", (), {"META": {"HTTP_X_API_KEY": "invalid_key"}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid API key" in str(exc_info.value)


@pytest.mark.django_db
def test_node_api_key_authentication_missing_key():
    """Test node API key authentication with missing key."""
    auth = NodeAPIKeyAuthentication()

    # Test with missing key
    request = type("Request", (), {"META": {}})()
    result = auth.authenticate(request)

    assert result is None


@pytest.mark.django_db
def test_node_api_key_authentication_inactive_key(create_node_api_key):
    """Test node API key authentication with inactive key."""
    api_key = create_node_api_key()
    api_key.is_active = False
    api_key.save()

    auth = NodeAPIKeyAuthentication()

    # Test authentication
    request = type("Request", (), {"META": {"HTTP_X_API_KEY": api_key.key}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid API key" in str(exc_info.value)
