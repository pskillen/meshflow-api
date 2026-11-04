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
import logging
import re
import zlib
from datetime import datetime, timedelta, timezone

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


# --- Protection against a stale feeder NodeDB upload overwriting a newer on-air name ----------------------
#
# A feeder uploads its radio's whole NodeDB on connect. That NodeDB is often stale or holds a placeholder
# (``Meshtastic 5abc`` / ``5abc``), while the API may already have a newer name from an on-air NODEINFO.
# Only the NodeDB upload path uses this; an on-air NODEINFO is the source of truth and is not filtered here.

NAME_FIELDS = ("long_name", "short_name")

logger = logging.getLogger(__name__)


def is_placeholder_name(name: str | None, node_id: int | None, field: str) -> bool:
    """True if ``name`` is the firmware default for the node: ``Meshtastic xxxx`` (long) or ``xxxx`` (short).

    ``xxxx`` is the last four hex digits of the node number. A blank name does not count (see ``is_blank``).
    """
    if not name or node_id is None:
        return False
    suffix = f"{node_id & 0xFFFFFFFF:08x}"[-4:]
    value = name.strip().lower()
    if field == "long_name":
        return value == f"meshtastic {suffix}"
    return value == suffix


def _is_real_name(name: str | None, node_id: int | None, field: str) -> bool:
    return bool(name and name.strip()) and not is_placeholder_name(name, node_id, field)


def protect_stale_names(instance, data: dict, latest_nodeinfo_time: datetime | None = None) -> dict:
    """Return ``data`` without NodeDB-upload names that would replace a newer or better stored name.

    For each of ``long_name`` / ``short_name`` present in ``data`` and a stored real name (not blank, not the
    placeholder) on ``instance``:

    * an incoming blank or placeholder name is dropped, always;
    * if the upload carries ``last_heard`` and the node's latest on-air NODEINFO (``latest_nodeinfo_time``) is
      newer, the incoming name is dropped. An upload with no ``last_heard`` cannot be dated, so a different
      real name is let through.

    A node with no real stored name is always filled. ``instance`` None (create) changes nothing.
    """
    if instance is None:
        return dict(data)
    kept = dict(data)
    node_id = getattr(instance, "meshtastic_node_id", None)
    last_heard = kept.get("last_heard")
    stale = bool(last_heard and latest_nodeinfo_time and latest_nodeinfo_time > last_heard)
    for field in NAME_FIELDS:
        if field not in kept:
            continue
        stored = getattr(instance, field, None)
        incoming = kept[field]
        if incoming == stored or not _is_real_name(stored, node_id, field):
            continue
        if not _is_real_name(incoming, node_id, field):
            reason = "incoming name is blank or a placeholder"
        elif stale:
            reason = "on-air NODEINFO is newer than the NodeDB entry"
        else:
            continue
        logger.debug("Kept %s %r for node %s over NodeDB upload %r: %s", field, stored, node_id, incoming, reason)
        del kept[field]
    return kept


# --- last_heard from a NodeDB upload must never move backwards or into the future ---------------------------

MAX_LAST_HEARD_FUTURE = timedelta(minutes=10)


def clamp_last_heard(instance, data: dict, now: datetime | None = None) -> dict:
    """Return ``data`` with ``last_heard`` made safe to store from a (often stale) feeder NodeDB upload.

    An incoming value more than 10 minutes in the future (bad radio clock) is dropped; one not newer than the
    stored value is dropped, so the stored value never moves backwards. ``instance`` None (create) only applies
    the future rule. Use the incoming value for ``protect_stale_names`` *before* calling this.
    """
    if data.get("last_heard") is None:
        return dict(data)
    kept = dict(data)
    incoming = kept["last_heard"]
    now = now or datetime.now(timezone.utc)
    stored = getattr(instance, "last_heard", None) if instance is not None else None
    if incoming > now + MAX_LAST_HEARD_FUTURE:
        logger.debug("Ignored NodeDB last_heard %s more than 10 minutes in the future", incoming)
        del kept["last_heard"]
    elif stored is not None and incoming <= stored:
        del kept["last_heard"]
    return kept
