"""Tests for common.meshtastic_identity (public key normalisation and predicted 2.8 node id)."""

import base64

import pytest

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import (
    clamp_last_heard,
    identity_fields,
    is_blank_mac,
    is_placeholder_name,
    is_truncated_long_name,
    key_node_id,
    normalise_pubkey,
    protect_identity,
    protect_stale_names,
)

# Key from docs/packets/nodeinfo_packet.json (NodeInfo from !da545c78 "JPPX Home").
WORKED_EXAMPLE_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
WORKED_EXAMPLE_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
WORKED_EXAMPLE_PREDICTED = "!4396524c"


def test_worked_example_predicts_expected_id():
    """!da545c78 is predicted to become !4396524c (zlib equivalence still unverified on hardware)."""
    assert meshtastic_id_to_hex(key_node_id(WORKED_EXAMPLE_B64)) == WORKED_EXAMPLE_PREDICTED


def test_base64_and_hex_agree():
    assert normalise_pubkey(WORKED_EXAMPLE_B64) == WORKED_EXAMPLE_HEX
    assert normalise_pubkey(WORKED_EXAMPLE_HEX) == WORKED_EXAMPLE_HEX
    assert key_node_id(WORKED_EXAMPLE_B64) == key_node_id(WORKED_EXAMPLE_HEX)


def test_hex_is_lowercased_and_stripped():
    assert normalise_pubkey(f"  {WORKED_EXAMPLE_HEX.upper()}\n") == WORKED_EXAMPLE_HEX


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "not a key!",
        "zz" * 32,  # 64 chars, not hex, not valid base64 of 32 bytes
        "abcd",  # valid base64 / hex-ish, wrong length
        base64.b64encode(b"\x01" * 31).decode(),
        base64.b64encode(b"\x01" * 33).decode(),
        ("ab" * 31),  # 62 hex chars
        ("ab" * 33),  # 66 hex chars
        12345,
    ],
)
def test_malformed_or_wrong_length_keys_give_none(bad):
    assert normalise_pubkey(bad) is None
    assert key_node_id(bad) is None
    assert identity_fields(bad) == {"meshtastic_public_key_hex": None, "meshtastic_key_node_id": None}


def test_identity_fields_for_good_key():
    assert identity_fields(WORKED_EXAMPLE_B64) == {
        "meshtastic_public_key_hex": WORKED_EXAMPLE_HEX,
        "meshtastic_key_node_id": 0x4396524C,
    }


# --- clobber protection (ID-8) ---

LONG = "Highland Ridge Repeater North-East"  # 34 bytes
LONG_PREFIX = LONG.encode()[:24].decode()  # "Highland Ridge Repeater N"


@pytest.mark.parametrize("mac", [None, "", "  ", "00:00:00:00:00:00", "000000000000", "AAAAAAAA", "00-00-00-00-00-00"])
def test_is_blank_mac_true(mac):
    assert is_blank_mac(mac)


@pytest.mark.parametrize("mac", ["a0:b3:a9:cf:5a:7b", "A0B3A9CF5A7B", "oLOpz1p7"])
def test_is_blank_mac_false(mac):
    assert not is_blank_mac(mac)


def test_truncated_long_name_ascii():
    assert is_truncated_long_name(LONG_PREFIX, LONG)


def test_truncated_long_name_genuine_renames_not_matched():
    assert not is_truncated_long_name("Short", "Short")
    assert not is_truncated_long_name("Sho", "Short")  # stored fits in 24 bytes: a genuine rename
    assert not is_truncated_long_name("Totally Different Name Here", LONG)
    assert not is_truncated_long_name("Highland Ridge", LONG)  # not the 24-byte prefix: genuine rename


def test_truncated_long_name_multibyte_split_mid_character():
    stored = "Café Ünïcödé NødeÅlesund Relay"  # multibyte characters straddle the 24-byte boundary
    raw = stored.encode()[:24]
    with pytest.raises(UnicodeDecodeError):
        raw.decode()  # the cut does land inside a character
    assert is_truncated_long_name(raw.decode(errors="ignore"), stored)
    assert is_truncated_long_name(raw.decode(errors="replace"), stored)


def test_protect_identity_drops_clobbering_values():
    class Stored:
        long_name = LONG

    data = {
        "mac_addr": "00:00:00:00:00:00",
        "meshtastic_public_key": "",
        "long_name": LONG_PREFIX,
        "short_name": "ABCD",
    }
    assert protect_identity(Stored(), data) == {"short_name": "ABCD"}


def test_protect_identity_keeps_real_changes():
    class Stored:
        long_name = LONG

    data = {"mac_addr": "a0:b3:a9:cf:5a:7b", "meshtastic_public_key": WORKED_EXAMPLE_B64, "long_name": "Renamed"}
    assert protect_identity(Stored(), data) == data


def test_is_placeholder_name_matches_last_four_hex_digits():
    assert is_placeholder_name("Meshtastic 5abc", 0x7D085ABC, "long_name")
    assert is_placeholder_name("meshtastic 5ABC", 0x7D085ABC, "long_name")
    assert is_placeholder_name("5abc", 0x7D085ABC, "short_name")
    assert not is_placeholder_name("Meshtastic 1234", 0x7D085ABC, "long_name")
    assert not is_placeholder_name("TIGERBAWS", 0x7D085ABC, "long_name")
    assert not is_placeholder_name("", 0x7D085ABC, "long_name")


def test_protect_stale_names_create_is_untouched():
    data = {"long_name": "Meshtastic 5abc"}
    assert protect_stale_names(None, data) == data


class _Stored:
    meshtastic_node_id = 0x7D085ABC
    long_name = "TIGERBAWS"
    short_name = "TIGR"


def test_protect_stale_names_blank_never_replaces_real_name():
    assert protect_stale_names(_Stored(), {"long_name": "", "short_name": None}) == {}


def test_protect_stale_names_without_timestamp_lets_real_name_through():
    data = {"long_name": "Renamed", "short_name": "RENM"}
    assert protect_stale_names(_Stored(), data) == data


def test_clamp_last_heard_rules():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    class Node:
        last_heard = now

    assert clamp_last_heard(Node(), {"last_heard": now - timedelta(hours=1)}, now) == {}
    newer = {"last_heard": now + timedelta(minutes=5)}
    assert clamp_last_heard(Node(), newer, now) == newer
    assert clamp_last_heard(Node(), {"last_heard": now + timedelta(minutes=11)}, now) == {}
    assert clamp_last_heard(None, {"last_heard": now + timedelta(minutes=11)}, now) == {}
    old = {"last_heard": now - timedelta(days=9)}
    assert clamp_last_heard(None, old, now) == old
