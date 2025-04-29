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

    assert user == api_key.owner
    assert auth_key == api_key


@pytest.mark.django_db
def test_node_api_key_authentication_valid_token(create_node_api_key):
    """Test node API key authentication with valid token format."""
    api_key = create_node_api_key()
    auth = NodeAPIKeyAuthentication()

    # Test authentication with Token format
    request = type("Request", (), {"META": {"HTTP_AUTHORIZATION": f"Token {api_key.key}"}})()
    user, auth_key = auth.authenticate(request)

    assert user == api_key.owner
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
def test_node_api_key_authentication_invalid_token():
    """Test node API key authentication with invalid token format."""
    auth = NodeAPIKeyAuthentication()

    # Test with invalid token format
    request = type("Request", (), {"META": {"HTTP_AUTHORIZATION": "Token invalid_key"}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid API key" in str(exc_info.value)


@pytest.mark.django_db
def test_node_api_key_authentication_missing_key():
    """Test node API key authentication with missing key."""
    auth = NodeAPIKeyAuthentication()

    # Test with missing key
    request = type("Request", (), {"META": {}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid authorization header: use Token <key> (or preferably x-api-key)" in str(exc_info.value)


@pytest.mark.django_db
def test_node_api_key_authentication_empty_key():
    """Test node API key authentication with empty key."""
    auth = NodeAPIKeyAuthentication()

    # Test with empty key
    request = type("Request", (), {"META": {"HTTP_X_API_KEY": ""}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid authorization header: use Token <key> (or preferably x-api-key)" in str(exc_info.value)


@pytest.mark.django_db
def test_node_api_key_authentication_empty_token():
    """Test node API key authentication with empty token."""
    auth = NodeAPIKeyAuthentication()

    # Test with empty token
    request = type("Request", (), {"META": {"HTTP_AUTHORIZATION": "Token "}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "API key is required" in str(exc_info.value)


@pytest.mark.django_db
def test_node_api_key_authentication_invalid_auth_format():
    """Test node API key authentication with invalid authorization format."""
    auth = NodeAPIKeyAuthentication()

    # Test with invalid authorization format
    request = type("Request", (), {"META": {"HTTP_AUTHORIZATION": "Bearer token"}})()
    with pytest.raises(Exception) as exc_info:
        auth.authenticate(request)

    assert "Invalid authorization header" in str(exc_info.value)


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


@pytest.mark.django_db
def test_node_api_key_authentication_prefer_x_api_key(create_node_api_key):
    """Test that X-API-KEY header is preferred over Authorization header."""
    api_key = create_node_api_key()
    auth = NodeAPIKeyAuthentication()

    # Test with both headers, X-API-KEY should be used
    request = type(
        "Request",
        (),
        {
            "META": {
                "HTTP_X_API_KEY": api_key.key,
                "HTTP_AUTHORIZATION": "Token invalid_key",
            }
        },
    )()
    user, auth_key = auth.authenticate(request)

    assert user == api_key.owner
    assert auth_key == api_key
