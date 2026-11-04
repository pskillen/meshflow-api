import pytest

from common.protocol import Protocol
from common.ws_groups import managed_node_ws_group


@pytest.mark.django_db
def test_meshtastic_group_uses_internal_id_not_node_number(create_managed_node):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    before = managed_node_ws_group(node)
    assert before == f"node_mt_{node.internal_id}"
    node.meshtastic_node_id += 1
    node.save(update_fields=["meshtastic_node_id"])
    assert managed_node_ws_group(node) == before


@pytest.mark.django_db
def test_meshcore_group_uses_internal_id(create_managed_node):
    node = create_managed_node(protocol=Protocol.MESHCORE)
    assert managed_node_ws_group(node) == f"node_mc_{node.internal_id}"
