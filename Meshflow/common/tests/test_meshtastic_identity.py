"""Tests for common.meshtastic_identity (public key normalisation and predicted 2.8 node id)."""

import base64

import pytest

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import identity_fields, key_node_id, normalise_pubkey

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
