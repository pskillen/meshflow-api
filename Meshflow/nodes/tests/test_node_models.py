import pytest
from nodes.models import ManagedNode, ObservedNode, NodeAPIKey, NodeAuth


@pytest.mark.django_db
def test_managed_node_creation(create_managed_node):
    """Test managed node creation with valid data."""
    node = create_managed_node()
    assert node.node_id == 123456789
    assert node.name == "Test Managed Node"
    assert node.owner is not None
    assert node.constellation is not None
    assert node.node_id_str == "0x75bcd15"


@pytest.mark.django_db
def test_managed_node_str_representation(create_managed_node):
    """Test managed node string representation."""
    node = create_managed_node()
    expected_str = f"{node.node_id_str} {node.name} ({node.owner.username})"
    assert str(node) == expected_str


@pytest.mark.django_db
def test_observed_node_creation(create_observed_node):
    """Test observed node creation with valid data."""
    node = create_observed_node()
    assert node.node_id == 987654321
    assert node.long_name == "Test Observed Node"
    assert node.short_name == "TEST"
    assert node.mac_addr == "00:11:22:33:44:55"
    assert node.hw_model == "T-Beam"
    assert node.sw_version == "2.0.0"
    assert node.node_id_str == "0x3ade68b1"


@pytest.mark.django_db
def test_observed_node_str_representation(create_observed_node):
    """Test observed node string representation."""
    node = create_observed_node()
    expected_str = f"{node.short_name} ({node.node_id_str})"
    assert str(node) == expected_str


@pytest.mark.django_db
def test_node_api_key_creation(create_node_api_key):
    """Test node API key creation."""
    api_key = create_node_api_key()
    assert api_key.key is not None
    assert len(api_key.key) == 40  # 20 bytes in hex
    assert api_key.owner is not None
    assert api_key.constellation is not None
    assert api_key.created_by is not None
    assert api_key.is_active is True


@pytest.mark.django_db
def test_node_auth_creation(create_node_auth):
    """Test node authentication creation."""
    auth = create_node_auth()
    assert auth.api_key is not None
    assert auth.node is not None
    assert str(auth) == f"{auth.api_key.name} - {auth.node}" 