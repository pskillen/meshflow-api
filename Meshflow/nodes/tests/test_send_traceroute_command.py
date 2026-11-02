from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command

import pytest

from common.ws_groups import managed_node_ws_group


@pytest.mark.django_db
def test_send_traceroute_uses_managed_node_group(create_managed_node):
    node = create_managed_node()
    layer = MagicMock()
    sent = []

    async def _send(*args, **kwargs):
        sent.append(args)

    layer.group_send = _send
    with patch("nodes.management.commands.send_traceroute.get_channel_layer", return_value=layer):
        call_command("send_traceroute", "123", managed_node_id=node.meshtastic_node_id, stdout=StringIO())
    assert sent[0][0] == managed_node_ws_group(node)
