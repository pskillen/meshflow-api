"""Tests for MeshCore path segment display and segment resolution lookup."""

import pytest

from common.protocol import Protocol
from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packets.services.path_resolution import (
    bulk_format_path_hops,
    format_path_hops,
    path_known_for_segments,
    segment_identity_key,
)
from nodes.models import NodeLatestStatus, ObservedNode


@pytest.mark.django_db
def test_format_path_hops_unknown_status():
    hops = format_path_hops(["f3bc", "f1"])
    assert len(hops) == 2
    assert hops[0]["hash"] == "f3bc"
    assert hops[0]["status"] == "unknown"
    assert hops[0]["short_name"] is None
    assert hops[0]["candidates"] == []
    assert hops[1]["hash"] == "f1"


@pytest.mark.django_db
def test_format_path_hops_normalizes_hex():
    hops = format_path_hops(["0xF3BC"])
    assert hops[0]["hash"] == "f3bc"


@pytest.mark.django_db
def test_bulk_format_path_hops_dedupes():
    cache = bulk_format_path_hops(["aa", "aa", "bb"])
    assert segment_identity_key("aa") in cache
    assert segment_identity_key("bb") in cache
    assert cache[segment_identity_key("aa")]["status"] == "unknown"


@pytest.mark.django_db
def test_path_known_false_when_unresolved():
    cache = bulk_format_path_hops(["aa", "bb"])
    assert path_known_for_segments(["aa", "bb"], resolution_cache=cache) is False
    assert path_known_for_segments(None) is False


@pytest.mark.django_db
def test_bulk_format_path_hops_uses_segment_resolution_table():
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="a" * 64,
        mc_pubkey_prefix="a" * 12,
        long_name="Resolved Hop",
        short_name="RH",
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="f3bc",
        hash_size=2,
        status=SegmentStatus.RESOLVED,
        observed_node=node,
    )
    cache = bulk_format_path_hops([{"segment": "f3bc", "hash_mode": None, "hash_size": 2}])
    hop = cache[segment_identity_key("f3bc", hash_size=2)]
    assert hop["status"] == "resolved"
    assert hop["node_id_str"] == node.node_id_str
    assert hop["long_name"] == "Resolved Hop"
    assert hop["short_name"] == "RH"


@pytest.mark.django_db
def test_bulk_format_path_hops_respects_hash_mode_size_identity():
    node_a = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="a" * 64,
        mc_pubkey_prefix="a" * 12,
        long_name="Size 2",
    )
    node_b = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="b" * 64,
        mc_pubkey_prefix="b" * 12,
        long_name="Size 3",
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="ab",
        hash_size=2,
        status=SegmentStatus.RESOLVED,
        observed_node=node_a,
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="ab",
        hash_size=3,
        status=SegmentStatus.RESOLVED,
        observed_node=node_b,
    )
    cache = bulk_format_path_hops(
        [
            {"segment": "ab", "hash_mode": None, "hash_size": 2},
            {"segment": "ab", "hash_mode": None, "hash_size": 3},
        ]
    )
    assert cache[segment_identity_key("ab", hash_size=2)]["long_name"] == "Size 2"
    assert cache[segment_identity_key("ab", hash_size=3)]["long_name"] == "Size 3"


@pytest.mark.django_db
def test_auto_matcher_unique_suffix_resolves():
    prefix = "00000000beef"
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey=prefix + ("c" * 52),
        mc_pubkey_prefix=prefix,
        long_name="Unique Suffix",
        short_name="US",
    )
    NodeLatestStatus.objects.create(node=node, latitude=55.0, longitude=-4.0)
    cache = bulk_format_path_hops([{"segment": "beef", "hash_mode": None, "hash_size": 2}])
    hop = cache[segment_identity_key("beef", hash_size=2)]
    assert hop["status"] == "resolved"
    assert hop["node_id_str"] == node.node_id_str
    assert hop["short_name"] == "US"


@pytest.mark.django_db
def test_auto_matcher_multiple_suffix_matches_ambiguous():
    ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="a" * 64,
        mc_pubkey_prefix="aaaaaaaacafe",
        long_name="Node A",
    )
    ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="b" * 64,
        mc_pubkey_prefix="bbbbbbbbcafe",
        long_name="Node B",
    )
    cache = bulk_format_path_hops([{"segment": "cafe", "hash_mode": None, "hash_size": 2}])
    hop = cache[segment_identity_key("cafe", hash_size=2)]
    assert hop["status"] == "ambiguous"
    assert hop["ambiguous"] is True
    assert len(hop["candidates"]) == 2


@pytest.mark.django_db
def test_manual_resolution_overrides_auto_matcher():
    prefix = "feedface0000"
    auto_node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey=prefix + ("d" * 52),
        mc_pubkey_prefix=prefix,
        long_name="Auto",
    )
    staff_node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="e" * 64,
        mc_pubkey_prefix="e" * 12,
        long_name="Staff",
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="face",
        hash_size=2,
        status=SegmentStatus.RESOLVED,
        observed_node=staff_node,
    )
    cache = bulk_format_path_hops([{"segment": "face", "hash_mode": None, "hash_size": 2}])
    hop = cache[segment_identity_key("face", hash_size=2)]
    assert hop["long_name"] == "Staff"
    assert hop["node_id_str"] != auto_node.node_id_str
