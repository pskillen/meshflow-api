"""Tests for meshcore_packets.services.path_hashes."""

from meshcore_packets.services.path_hashes import enrich_validated_data_paths, path_hashes_from_ingest, split_path_hex


def test_split_path_hex_two_byte_hops():
    assert split_path_hex("aabbccdd", 2) == ["aabb", "ccdd"]


def test_split_path_hex_three_byte_hop():
    assert split_path_hex("f3bcf1", 3) == ["f3bcf1"]


def test_path_hashes_from_ingest_top_level_path():
    data = {"path": "aabb", "path_hash_size": 2}
    assert path_hashes_from_ingest(data) == ["aabb"]


def test_path_hashes_from_nested_envelope():
    data = {
        "raw": {
            "protocol": "meshcore",
            "event_type": "rx_log_data",
            "payload": {
                "path": "f3bcf1",
                "path_hash_size": 3,
            },
        },
    }
    assert path_hashes_from_ingest(data) == ["f3bcf1"]


def test_enrich_validated_data_paths():
    data = {"path": "aabbcc", "path_hash_size": 2}
    enrich_validated_data_paths(data)
    assert data["path_hashes"] == ["aabb", "cc"]
