import pytest

from common.protocol import Protocol
from nodes.models import NodeAuth


@pytest.fixture
def meshcore_feeder(create_managed_node, create_node_api_key):
    """MC ManagedNode + API key + NodeAuth for ingest tests."""
    node = create_managed_node(meshtastic_node_id=0, protocol=Protocol.MESHCORE, name="MC Feeder")
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return {"node": node, "api_key": api_key}
