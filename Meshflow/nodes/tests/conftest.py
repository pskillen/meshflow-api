import pytest
from nodes.models import ManagedNode, ObservedNode, NodeAPIKey, NodeAuth
from users.tests.conftest import create_user


@pytest.fixture
def managed_node_data():
    return {
        "node_id": 123456789,
        "name": "Test Managed Node",
    }


@pytest.fixture
def observed_node_data():
    return {
        "node_id": 987654321,
        "long_name": "Test Observed Node",
        "short_name": "TEST",
        "mac_addr": "00:11:22:33:44:55",
        "hw_model": "T-Beam",
        "sw_version": "2.0.0",
    }


@pytest.fixture
def create_managed_node(create_user, managed_node_data):
    def make_managed_node(**kwargs):
        data = managed_node_data.copy()
        data.update(kwargs)
        if "owner" not in data:
            data["owner"] = create_user()
        if "constellation" not in data:
            data["constellation"] = create_user().constellations.first()
        return ManagedNode.objects.create(**data)
    return make_managed_node


@pytest.fixture
def create_observed_node(observed_node_data):
    def make_observed_node(**kwargs):
        data = observed_node_data.copy()
        data.update(kwargs)
        return ObservedNode.objects.create(**data)
    return make_observed_node


@pytest.fixture
def create_node_api_key(create_user):
    def make_api_key(**kwargs):
        if "constellation" not in kwargs:
            kwargs["constellation"] = create_user().constellations.first()
        if "owner" not in kwargs:
            kwargs["owner"] = create_user()
        if "created_by" not in kwargs:
            kwargs["created_by"] = kwargs["owner"]
        return NodeAPIKey.objects.create(**kwargs)
    return make_api_key


@pytest.fixture
def create_node_auth(create_managed_node, create_node_api_key):
    def make_node_auth(**kwargs):
        if "api_key" not in kwargs:
            kwargs["api_key"] = create_node_api_key()
        if "node" not in kwargs:
            kwargs["node"] = create_managed_node()
        return NodeAuth.objects.create(**kwargs)
    return make_node_auth 