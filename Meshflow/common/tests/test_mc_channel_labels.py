"""Tests for MeshCore channel admin labels and apply payloads."""

import pytest

from common.mc_channel_labels import (
    mc_channel_admin_label,
    mc_channel_mirror_label,
    mc_channel_scope_display,
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
        mc_channel_type=MeshCoreChannelType.HASHTAG,
    )
    assert mc_channel_admin_label(ch) == "#galloway"


@pytest.mark.django_db
def test_mc_channel_admin_label_hashtag_with_scope(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="galloway",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        region_scope="sample-west",
    )
    assert mc_channel_admin_label(ch) == "#galloway · sample-west"


@pytest.mark.django_db
def test_mc_channel_mirror_label_and_scope_display(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="galloway",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        region_scope="sample-west",
    )
    assert mc_channel_mirror_label(ch) == "#galloway"
    assert mc_channel_scope_display(ch) == "sample-west"
    ch.region_scope = None
    assert mc_channel_scope_display(ch) == "—"


@pytest.mark.django_db
def test_message_channel_to_apply_entry_hashtag(create_constellation):
    constellation = create_constellation()
    ch = MessageChannel.objects.create(
        name="galloway",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.HASHTAG,
        region_scope="sample-west",
    )
    entry = message_channel_to_apply_entry(ch, mc_channel_idx=1)
    assert entry["mc_channel_type"] == "HASHTAG"
    assert entry["name"] == "galloway"
    assert entry["region_scope"] == "sample-west"
