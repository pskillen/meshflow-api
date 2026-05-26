from itertools import count

from django.utils import timezone

import pytest

from common.protocol import Protocol
from constellations.models import MessageChannel
from constellations.tests.conftest import create_constellation  # noqa: F401
from nodes.models import ManagedNode, ManagedNodeStatus, NodeAPIKey, NodeAuth, ObservedNode
from users.tests.conftest import create_user  # noqa: F401

_mt_managed_node_id_seq = count(0x10000000)


def _coerce_meshtastic_node_id_kwargs(data: dict, explicit_keys: set, *, managed: bool = False) -> dict:
    """Map legacy test kwarg ``node_id`` to ``meshtastic_node_id`` (SP-03)."""
    if "node_id" in data:
        if "meshtastic_node_id" in data:
            raise ValueError("Pass only one of node_id or meshtastic_node_id")
        data["meshtastic_node_id"] = data.pop("node_id")
        explicit_keys = set(explicit_keys) | {"meshtastic_node_id"}
    protocol = data.get("protocol", Protocol.MESHTASTIC)
    if protocol == Protocol.MESHCORE:
        if "meshtastic_node_id" not in explicit_keys or data.get("meshtastic_node_id") == 0:
            data["meshtastic_node_id"] = None
        if not data.get("mc_pubkey"):
            data["mc_pubkey"] = "a" * 64
    elif managed and "meshtastic_node_id" not in explicit_keys:
        data["meshtastic_node_id"] = next(_mt_managed_node_id_seq)
    return data


_LEGACY_OBSERVED_NODE_FIELD_ALIASES = {
    "hw_model": "meshtastic_hw_model",
    "public_key": "meshtastic_public_key",
    "role": "meshtastic_role",
    "is_licensed": "meshtastic_is_licensed",
    "is_unmessagable": "meshtastic_is_unmessagable",
}


def _coerce_observed_node_legacy_kwargs(data: dict) -> dict:
    """Map legacy test kwargs to ``meshtastic_*`` field names (SP-04)."""
    _coerce_meshtastic_node_id_kwargs(data, set(), managed=False)
    for old, new in _LEGACY_OBSERVED_NODE_FIELD_ALIASES.items():
        if old in data:
            if new in data:
                raise ValueError(f"Pass only one of {old} or {new}")
            data[new] = data.pop(old)
    return data


@pytest.fixture
def constellation_data():
    return {
        "name": "Test Constellation",
        "description": "Test Description",
    }


@pytest.fixture
def managed_node_data():
    return {
        "meshtastic_node_id": 123456789,
        "name": "Test Managed Node",
    }


@pytest.fixture
def observed_node_data():
    return {
        "meshtastic_node_id": 987654321,
        "long_name": "Test Observed Node",
        "short_name": "TEST",
        "mac_addr": "00:11:22:33:44:55",
        "meshtastic_hw_model": "T-Beam",
    }


@pytest.fixture
def create_managed_node(managed_node_data, create_user, create_constellation):  # noqa: F811
    def make_managed_node(**kwargs):
        data = managed_node_data.copy()
        data.update(kwargs)
        _coerce_meshtastic_node_id_kwargs(data, set(kwargs.keys()), managed=True)
        if "owner" not in data:
            data["owner"] = create_user()
        if "constellation" not in data:
            data["constellation"] = create_constellation(created_by=data["owner"])

        # only add 2 channels, we don't need all 8
        if "meshtastic_channel_0" not in data:
            data["meshtastic_channel_0"] = MessageChannel.objects.create(
                name="Channel 0",
                constellation=data["constellation"],
            )
        if "meshtastic_channel_1" not in data:
            data["meshtastic_channel_1"] = MessageChannel.objects.create(
                name="Channel 1",
                constellation=data["constellation"],
            )

        return ManagedNode.objects.create(**data)

    return make_managed_node


@pytest.fixture
def create_observed_node(observed_node_data):
    def make_observed_node(**kwargs):
        data = observed_node_data.copy()
        data.update(kwargs)
        _coerce_observed_node_legacy_kwargs(data)
        data.pop("node_id_str", None)
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
        for mn in ManagedNode.objects.filter(constellation=constellation, deleted_at__isnull=True):
            mark_managed_node_feeding(mn, sending=True)

    return _mark


FEEDER_MC_PUBKEY = "a" * 64
FEEDER_MC_PUBKEY_PREFIX = "a" * 12


@pytest.fixture
def meshcore_feeder(create_managed_node, create_node_api_key):
    """MC ManagedNode + API key + NodeAuth for ingest and stats tests."""
    node = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder",
        mc_pubkey=FEEDER_MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return {
        "node": node,
        "api_key": api_key,
        "feeder_pubkey_prefix": FEEDER_MC_PUBKEY_PREFIX,
    }
