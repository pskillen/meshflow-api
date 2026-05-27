"""MeshCore channel sender label parsing and candidate lookup."""

from django.utils import timezone

import pytest

from common.protocol import Protocol
from nodes.models import MeshCoreLocationSource, NodeLatestStatus, ObservedNode, Position
from text_messages.mc_channel_sender import (
    bulk_mc_sender_candidates_by_label,
    mc_sender_candidates_for_message,
    parse_mc_channel_sender_label,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Alice: hello mesh", "Alice"),
        ("Bob: ", None),
        ("No colon here", None),
        ("Bad:no space", None),
    ],
)
def test_parse_mc_channel_sender_label(text, expected):
    assert parse_mc_channel_sender_label(text) == expected


@pytest.mark.django_db
def test_mc_sender_candidates_match_long_and_short_name():
    node_a = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="a" * 64,
        mc_pubkey_prefix="a" * 12,
        long_name="WMF",
        short_name="WMF",
        last_heard=None,
    )
    NodeLatestStatus.objects.create(node=node_a, latitude=55.1, longitude=-4.1)
    ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="b" * 64,
        mc_pubkey_prefix="b" * 12,
        long_name="Other",
        short_name="OTHR",
        last_heard=None,
    )
    dup = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="c" * 64,
        mc_pubkey_prefix="c" * 12,
        long_name="WMF",
        short_name="WM2",
        last_heard=None,
    )
    candidates = mc_sender_candidates_for_message("WMF: ping")
    ids = {c["internal_id"] for c in candidates}
    assert str(node_a.internal_id) in ids
    assert str(dup.internal_id) in ids
    assert len(candidates) == 2
    assert candidates[0]["position"] is not None or candidates[1]["position"] is not None


@pytest.mark.django_db
def test_mc_sender_candidate_position_from_latest_position_row():
    """Position when only Position history exists (NodeLatestStatus empty)."""
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="e" * 64,
        mc_pubkey_prefix="e" * 12,
        long_name="MapNode",
        short_name="MAP",
        last_heard=None,
    )
    NodeLatestStatus.objects.create(node=node, latitude=None, longitude=None)
    now = timezone.now()
    Position.objects.create(
        node=node,
        reported_time=now,
        logged_time=now,
        latitude=55.99,
        longitude=-4.09,
        meshcore_location_source=MeshCoreLocationSource.ADVERT,
    )
    candidates = mc_sender_candidates_for_message("MapNode: test")
    assert len(candidates) == 1
    assert candidates[0]["position"] == {"latitude": 55.99, "longitude": -4.09}


@pytest.mark.django_db
def test_bulk_mc_sender_candidates_by_label():
    ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="d" * 64,
        mc_pubkey_prefix="d" * 12,
        long_name="Zed",
        short_name="ZED",
        last_heard=None,
    )
    result = bulk_mc_sender_candidates_by_label({"Zed", "Missing"})
    assert len(result["Zed"]) == 1
    assert result["Missing"] == []
