"""Helper functions for working with Meshtastic node IDs and timestamps."""

import base64

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
