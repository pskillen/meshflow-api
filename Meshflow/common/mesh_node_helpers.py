"""Meshtastic-specific helpers for node IDs and the MT broadcast sentinel.

MeshCore broadcast semantics differ; see docs/features/packet-ingestion/adr/0003-mc-broadcast-semantics.md.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from common.protocol import Protocol

if TYPE_CHECKING:
    from nodes.models import ObservedNode

MESHTASTIC_BROADCAST_ID = 0xFFFFFFFF

MT_NODE_ID_STR_PREFIX = "mt:"

# Deprecated alias — prefer MESHTASTIC_BROADCAST_ID; remove once all call sites are migrated.
BROADCAST_ID = MESHTASTIC_BROADCAST_ID


def normalize_meshtastic_lookup_hex(token: str) -> str | None:
    """Extract 8-char Meshtastic hex from ``!…``, ``mt:…``, or bare suffix."""
    t = token.strip()
    lower = t.lower()
    if lower.startswith(MT_NODE_ID_STR_PREFIX):
        t = t[len(MT_NODE_ID_STR_PREFIX) :]
    elif t.startswith("!"):
        t = t[1:]
    t = t.lower().replace("0x", "")
    if len(t) == 8 and all(c in "0123456789abcdef" for c in t):
        return t
    return None


def meshtastic_id_to_hex(meshtastic_id: int) -> str:
    """Convert a Meshtastic ID (integer form) to hex representation (!abcdef12)."""
    if meshtastic_id == MESHTASTIC_BROADCAST_ID:
        return "^all"

    return f"!{meshtastic_id:08x}"


def observed_node_search_conditions(query: str):
    """Build Q filters for ObservedNode search (display id, names, numeric MT id)."""
    from django.db.models import Q

    from common.meshcore_node_helpers import MC_NODE_ID_STR_PREFIX, normalize_mc_pubkey_prefix

    conditions = Q()
    q = query.strip()

    if q.startswith("!") and len(q) == 9:
        try:
            conditions |= Q(meshtastic_node_id=meshtastic_hex_to_int(q))
        except ValueError:
            pass
    elif q.lower().startswith(MC_NODE_ID_STR_PREFIX):
        suffix = q[len(MC_NODE_ID_STR_PREFIX) :].strip().lower().replace("0x", "")
        if suffix:
            try:
                if len(suffix) == 12:
                    prefix = normalize_mc_pubkey_prefix(suffix)
                    conditions |= Q(mc_pubkey_prefix=prefix) | Q(mc_pubkey__istartswith=prefix)
                else:
                    conditions |= Q(mc_pubkey_prefix__icontains=suffix) | Q(mc_pubkey__icontains=suffix)
            except ValueError:
                conditions |= Q(mc_pubkey_prefix__icontains=suffix) | Q(mc_pubkey__icontains=suffix)
    elif q.startswith("!"):
        try:
            conditions |= Q(meshtastic_node_id=meshtastic_hex_to_int(q))
        except ValueError:
            pass
    else:
        hexish = q.lower().replace("0x", "")
        if hexish and all(c in "0123456789abcdef" for c in hexish):
            conditions |= Q(mc_pubkey__icontains=hexish) | Q(mc_pubkey_prefix__icontains=hexish)

    try:
        conditions |= Q(meshtastic_node_id=int(q))
    except ValueError, TypeError:
        pass

    conditions |= Q(short_name__icontains=query)
    conditions |= Q(long_name__icontains=query)
    return conditions


def observed_node_id_str(node: ObservedNode) -> str:
    """Protocol-aware display id for an ObservedNode (ADR-0001; not persisted)."""
    from common.meshcore_node_helpers import mc_node_id_str

    if node.protocol == Protocol.MESHCORE:
        return mc_node_id_str(mc_pubkey=node.mc_pubkey, mc_pubkey_prefix=node.mc_pubkey_prefix)
    if node.meshtastic_node_id is None:
        raise ValueError("Meshtastic ObservedNode requires meshtastic_node_id")
    return meshtastic_id_to_hex(node.meshtastic_node_id)


def meshtastic_hex_to_int(node_id: str) -> int:
    """Convert a Meshtastic ID (hex representation) to integer form."""
    if node_id == "^all":
        return MESHTASTIC_BROADCAST_ID

    return int(node_id[1:], 16)


def parse_b64_mac_address(mac_b64: str) -> str:
    """Parse a base64 encoded MAC address.

    Args:
        mac_b64: Base64 encoded MAC address

    Returns:
        MAC address in colon-separated hex format (e.g., "00:11:22:33:44:55")

    Raises:
        ValueError: If the input is empty or invalid
    """
    if not mac_b64:
        raise ValueError("Empty MAC address")

    try:
        mac_bytes = base64.b64decode(mac_b64)
        if not mac_bytes:
            raise ValueError("Invalid MAC address: decoded to empty bytes")
        mac_str = ":".join(f"{b:02x}" for b in mac_bytes)
        return mac_str
    except Exception as e:
        raise ValueError(f"Invalid MAC address: {str(e)}")
