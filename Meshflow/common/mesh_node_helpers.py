"""Helper functions for working with Meshtastic node IDs and timestamps."""

from datetime import datetime, timezone

BROADCAST_ID = 0xFFFFFFFF


def meshtastic_id_to_hex(meshtastic_id: int) -> str:
    """Convert a Meshtastic ID (integer form) to hex representation (!abcdef12)."""
    if meshtastic_id == BROADCAST_ID:
        return "^all"

    return f"!{meshtastic_id:08x}"


def meshtastic_hex_to_int(node_id: str) -> int:
    """Convert a Meshtastic ID (hex representation) to integer form."""
    if node_id == "^all":
        return BROADCAST_ID

    return int(node_id[1:], 16)

