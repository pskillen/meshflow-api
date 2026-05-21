import pytest

from common.protocol import Protocol
from nodes.models import NodeAuth

FEEDER_MC_PUBKEY = "a" * 64
FEEDER_MC_PUBKEY_PREFIX = "a" * 12
FEEDER_B_MC_PUBKEY = "c" * 64
FEEDER_B_MC_PUBKEY_PREFIX = "c" * 12


@pytest.fixture
def meshcore_feeder(create_managed_node, create_node_api_key):
    """MC ManagedNode + API key + NodeAuth for ingest tests."""
    node = create_managed_node(
        meshtastic_node_id=0,
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


def feeder_url(name: str, prefix: str) -> str:
    """Reverse feeder-scoped meshcore URL."""
    from django.urls import reverse

    return reverse(name, kwargs={"feeder_pubkey_prefix": prefix})
