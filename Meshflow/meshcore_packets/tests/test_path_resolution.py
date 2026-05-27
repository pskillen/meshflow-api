"""Tests for MeshCore path segment display (v1)."""

from meshcore_packets.services.path_resolution import (
    bulk_format_path_hops,
    format_path_hops,
    path_known_for_segments,
)


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
    }
    assert hops[1]["hash"] == "f1"


def test_format_path_hops_normalizes_hex():
    hops = format_path_hops(["0xF3BC"])
    assert hops[0]["hash"] == "f3bc"


def test_bulk_format_path_hops_dedupes():
    cache = bulk_format_path_hops(["aa", "aa", "bb"])
    assert set(cache.keys()) == {"aa", "bb"}
    assert cache["aa"]["status"] == "unknown"


def test_path_known_false_in_v1():
    assert path_known_for_segments(["aa", "bb"]) is False
    assert path_known_for_segments(None) is False
