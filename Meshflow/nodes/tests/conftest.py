from django.utils import timezone

import pytest

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import MessageChannel
from constellations.tests.conftest import create_constellation  # noqa: F401
from nodes.models import ManagedNode, ManagedNodeStatus, NodeAPIKey, NodeAuth, ObservedNode
from users.tests.conftest import create_user  # noqa: F401


@pytest.fixture
def constellation_data():
    return {
        "name": "Test Constellation",
        "description": "Test Description",
    }


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
    }


@pytest.fixture
def create_managed_node(managed_node_data, create_user, create_constellation):  # noqa: F811
    def make_managed_node(**kwargs):
        data = managed_node_data.copy()
        data.update(kwargs)
        if "owner" not in data:
            data["owner"] = create_user()
        if "constellation" not in data:
            data["constellation"] = create_constellation(created_by=data["owner"])

        # only add 2 channels, we don't need all 8
        if "channel_0" not in data:
            data["channel_0"] = MessageChannel.objects.create(
                name="Channel 0",
                constellation=data["constellation"],
            )
        if "channel_1" not in data:
            data["channel_1"] = MessageChannel.objects.create(
                name="Channel 1",
                constellation=data["constellation"],
            )

        return ManagedNode.objects.create(**data)

    return make_managed_node


@pytest.fixture
def create_observed_node(observed_node_data):
    def make_observed_node(**kwargs):
        data = observed_node_data.copy()
        data["node_id_str"] = meshtastic_id_to_hex(data["node_id"])
        data.update(kwargs)
        return ObservedNode.objects.create(**data)

    return make_observed_node


@pytest.fixture
def create_node_api_key(create_user, create_constellation):  # noqa: F811
    def make_node_api_key(**kwargs):
        if "owner" not in kwargs:
            kwargs["owner"] = create_user()
        if "constellation" not in kwargs:
            kwargs["constellation"] = create_constellation(created_by=kwargs["owner"])
        if "name" not in kwargs:
            kwargs["name"] = "Test API Key"
        return NodeAPIKey.objects.create(**kwargs)

    return make_node_api_key


@pytest.fixture
def create_node_auth(create_node_api_key, create_managed_node):
    def make_node_auth(**kwargs):
        if "api_key" not in kwargs:
            kwargs["api_key"] = create_node_api_key()
        if "node" not in kwargs:
            kwargs["node"] = create_managed_node(owner=kwargs["api_key"].owner)
        return NodeAuth.objects.create(**kwargs)

    return make_node_auth


@pytest.fixture
def mark_managed_node_feeding():
    """Set denormalized feeder snapshot without going through packet ingestion."""

    def _mark(managed_node: ManagedNode, *, sending: bool = True, last_at=None):
        ts = last_at if last_at is not None else (timezone.now() if sending else None)
        ManagedNodeStatus.objects.update_or_create(
            node=managed_node,
            defaults={
                "last_packet_ingested_at": ts,
                "is_sending_data": sending,
            },
        )

    return _mark


@pytest.fixture
def mark_constellation_managed_nodes_feeding(mark_managed_node_feeding):
    """Mark every managed node in a constellation as actively feeding."""

    def _mark(constellation):
        for mn in ManagedNode.objects.filter(constellation=constellation):
            mark_managed_node_feeding(mn, sending=True)

    return _mark
