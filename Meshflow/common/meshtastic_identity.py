"""Meshtastic identity helpers: normalise stored public keys and predict the 2.8 node number.

Meshtastic 2.8 firmware derives a node's number from the CRC-32 of its 32-byte Curve25519 public key
(``NodeDB.cpp`` ``createNewIdentity()``). Upgrades reuse the existing private key, so the number a node
will have after upgrading can be predicted from a public key we already store.

NOTE: the firmware uses its own ``ErriezCRC32``. That ``zlib.crc32`` gives the same value is inferred from
source and the worked example (``!da545c78`` -> ``!4396524c``), and is **not yet confirmed on hardware**.
See docs/features/packet-ingestion/adr/0006-meshtastic-identity-linking.md.
"""

from __future__ import annotations

import base64
import binascii
import re
import zlib

PUBKEY_BYTES = 32
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _pubkey_bytes(pubkey: str | None) -> bytes | None:
    """Decode a stored key (64-char hex or base64) to exactly 32 raw bytes, else None. Never raises."""
    if not pubkey or not isinstance(pubkey, str):
        return None
    value = pubkey.strip()
    if _HEX64.match(value):
        return bytes.fromhex(value)
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        return None
    return raw if len(raw) == PUBKEY_BYTES else None


def normalise_pubkey(pubkey: str | None) -> str | None:
    """Return the key as 64-char lowercase hex, or None if malformed or not 32 bytes."""
    raw = _pubkey_bytes(pubkey)
    return raw.hex() if raw is not None else None


def key_node_id(pubkey: str | None) -> int | None:
    """Predict the 2.8 node number: ``crc32`` of the 32 raw key bytes, or None for a bad key."""
    raw = _pubkey_bytes(pubkey)
    if raw is None:
        return None
    return zlib.crc32(raw) & 0xFFFFFFFF


def identity_fields(pubkey: str | None) -> dict[str, str | int | None]:
    """Derived ObservedNode fields for a stored key (both None when the key is unusable)."""
    return {
        "meshtastic_public_key_hex": normalise_pubkey(pubkey),
        "meshtastic_key_node_id": key_node_id(pubkey),
    }
