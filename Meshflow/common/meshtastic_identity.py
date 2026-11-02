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


# --- Protection against 2.8 feeder NodeDB data clobbering good identity values -----------------------------
#
# 2.8 firmware hands feeders NodeDB entries with a zero-filled ``macaddr`` and a long name truncated to
# 24 bytes (``TypeConversions.cpp``). Those must never replace a real MAC / the full name / a stored key.

LONG_NAME_TRUNCATED_BYTES = 24


def is_blank_mac(mac: str | None) -> bool:
    """True for a missing, blank or all-zero MAC (``00:00:00:00:00:00``, ``000000000000``, base64 of 6 zero bytes)."""
    if mac is None or not isinstance(mac, str):
        return True
    value = mac.strip()
    if not value:
        return True
    if set(value) <= set("0:-. "):
        return True
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        return False
    return len(raw) == 6 and not any(raw)


def is_truncated_long_name(incoming: str | None, stored: str | None) -> bool:
    """True if ``incoming`` is only ``stored`` cut to 24 UTF-8 bytes (a different, shorter value).

    Truncation is byte-wise, so it can split a multibyte character; the bot may drop or replace the partial
    character when decoding, so both spellings count as the truncated prefix.
    """
    if not incoming or not stored or incoming == stored:
        return False
    stored_bytes = stored.encode("utf-8")
    if len(stored_bytes) <= LONG_NAME_TRUNCATED_BYTES:
        return False
    prefix = stored_bytes[:LONG_NAME_TRUNCATED_BYTES]
    # Whitespace is trimmed on both sides: the cut can leave a trailing space and DRF strips input strings.
    return incoming.strip() in {
        prefix.decode("utf-8", errors="ignore").strip(),
        prefix.decode("utf-8", errors="replace").strip(),
    }


def protect_identity(instance, data: dict) -> dict:
    """Return ``data`` (ObservedNode field names) without values that would clobber stored identity evidence.

    Drops a blank/all-zero ``mac_addr``, a blank ``meshtastic_public_key`` and a ``long_name`` that is just the
    24-byte prefix of the stored one. ``instance`` may be None (create): then only blank values are dropped.
    A dropped key also means its derived fields must not be rewritten: callers derive them from the result.
    """
    kept = dict(data)
    if "mac_addr" in kept and is_blank_mac(kept["mac_addr"]):
        del kept["mac_addr"]
    if "meshtastic_public_key" in kept and not (kept["meshtastic_public_key"] or "").strip():
        del kept["meshtastic_public_key"]
    if "long_name" in kept:
        if not kept["long_name"]:
            del kept["long_name"]
        elif instance is not None and is_truncated_long_name(kept["long_name"], instance.long_name):
            del kept["long_name"]
    return kept
