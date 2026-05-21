"""Tests for channel_apply service."""

from unittest.mock import AsyncMock, patch

import pytest

from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel
from meshcore_packets.services.channel_apply import build_apply_channels_for_managed_node


@pytest.mark.django_db
def test_build_apply_channels_for_managed_node(meshcore_feeder):
    node = meshcore_feeder["node"]
    constellation = node.constellation
    ch = MessageChannel.objects.create(
        name="tag",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=2,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        mc_hashtag="meshflow",
    )
    node.mc_channels.add(ch)

    payload = build_apply_channels_for_managed_node(node)
    assert len(payload) == 1
    assert payload[0]["mc_channel_idx"] == 2
    assert payload[0]["mc_channel_type"] == "HASHTAG"
    assert payload[0]["mc_hashtag"] == "meshflow"


@pytest.mark.django_db
def test_apply_mc_channels_to_feeder_dispatches(meshcore_feeder):
    from meshcore_packets.services.channel_apply import apply_mc_channels_to_feeder

    node = meshcore_feeder["node"]
    with (
        patch(
            "meshcore_packets.services.channel_apply.feeder_ws_group_has_subscribers",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "meshcore_packets.services.channel_apply.dispatch_node_command",
            new_callable=AsyncMock,
        ) as dispatch_mock,
    ):
        result = apply_mc_channels_to_feeder(node, [{"mc_channel_idx": 0, "name": "x", "mc_channel_type": "PUBLIC"}])

    assert result == "sent"
    dispatch_mock.assert_awaited_once()
