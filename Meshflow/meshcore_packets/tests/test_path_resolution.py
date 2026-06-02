"""Tests for MeshCore path segment display and segment resolution lookup."""

import pytest

from common.protocol import Protocol
from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packets.services.path_resolution import (
    bulk_format_path_hops,
    format_path_hops,
    path_known_for_segments,
)
from nodes.models import ObservedNode


def test_format_path_hops_unknown_status():
    hops = format_path_hops(["f3bc", "f1"])
    assert len(hops) == 2
    assert hops[0] == {
        "hash": "f3bc",
        "status": "unknown",
        "node_id_str": None,
        "internal_id": None,
        "long_name": None,
        "ambiguous": False,
        "position": None,
    }
    assert hops[1]["hash"] == "f1"


def test_format_path_hops_normalizes_hex():
    hops = format_path_hops(["0xF3BC"])
    assert hops[0]["hash"] == "f3bc"


@pytest.mark.django_db
def test_bulk_format_path_hops_dedupes():
    cache = bulk_format_path_hops(["aa", "aa", "bb"])
    assert set(cache.keys()) == {"aa", "bb"}
    assert cache["aa"]["status"] == "unknown"


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
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="f3bc",
        hash_size=2,
        status=SegmentStatus.RESOLVED,
        observed_node=node,
    )
    cache = bulk_format_path_hops(["f3bc"])
    hop = cache["f3bc"]
    assert hop["status"] == "resolved"
    assert hop["node_id_str"] == node.node_id_str
    assert hop["long_name"] == "Resolved Hop"
