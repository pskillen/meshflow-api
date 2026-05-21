"""Tests for MeshCore channel admin labels and apply payloads."""

import pytest

from common.mc_channel_labels import (
    mc_channel_admin_label,
    message_channel_to_apply_entry,
)
from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel


@pytest.mark.django_db
def test_mc_channel_admin_label_public(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="Public",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=0,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
    )
    assert mc_channel_admin_label(ch) == "Public"


@pytest.mark.django_db
def test_mc_channel_admin_label_hashtag_prefix(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="galloway",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=1,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        mc_hashtag="galloway",
    )
    assert mc_channel_admin_label(ch) == "#galloway"


@pytest.mark.django_db
def test_message_channel_to_apply_entry_hashtag(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="galloway",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=1,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        mc_hashtag="galloway",
    )
    entry = message_channel_to_apply_entry(ch)
    assert entry["mc_channel_type"] == "HASHTAG"
    assert entry["mc_hashtag"] == "galloway"
    assert entry["name"] == "galloway"
