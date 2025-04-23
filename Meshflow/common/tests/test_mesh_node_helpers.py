import pytest
from common.mesh_node_helpers import (
    meshtastic_id_to_hex,
    meshtastic_hex_to_int,
    parse_b64_mac_address,
    BROADCAST_ID
)


def test_meshtastic_id_to_hex():
    """Test conversion of Meshtastic ID to hex representation."""
    # Test regular node ID
    assert meshtastic_id_to_hex(0x12345678) == "!12345678"
    
    # Test broadcast ID
    assert meshtastic_id_to_hex(BROADCAST_ID) == "^all"
    
    # Test zero ID
    assert meshtastic_id_to_hex(0) == "!00000000"


def test_meshtastic_hex_to_int():
    """Test conversion of hex representation to Meshtastic ID."""
    # Test regular node ID
    assert meshtastic_hex_to_int("!12345678") == 0x12345678
    
    # Test broadcast ID
    assert meshtastic_hex_to_int("^all") == BROADCAST_ID
    
    # Test zero ID
    assert meshtastic_hex_to_int("!00000000") == 0


def test_parse_b64_mac_address():
    """Test parsing of base64 encoded MAC address."""
    # Test valid MAC address
    mac_b64 = "AAECAwQFBg=="  # Base64 for bytes [0, 1, 2, 3, 4, 5, 6]
    assert parse_b64_mac_address(mac_b64) == "00:01:02:03:04:05:06"
    
    # Test empty MAC address
    mac_b64 = ""  # Base64 for empty bytes
    with pytest.raises(ValueError, match="Empty MAC address"):
        parse_b64_mac_address(mac_b64)
        
    # Test invalid base64
    mac_b64 = "invalid_base64"
    with pytest.raises(ValueError, match="Invalid MAC address"):
        parse_b64_mac_address(mac_b64) 