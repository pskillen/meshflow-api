"""Meshtastic enum maps copied from the protobufs (reference: v2.8.2 ``portnums.proto``)."""

# ``PortNum.MAX`` (511) is a sentinel, not a port, and is left out.
PORTNUM_NAMES: dict[int, str] = {
    0: "UNKNOWN_APP",
    1: "TEXT_MESSAGE_APP",
    2: "REMOTE_HARDWARE_APP",
    3: "POSITION_APP",
    4: "NODEINFO_APP",
    5: "ROUTING_APP",
    6: "ADMIN_APP",
    7: "TEXT_MESSAGE_COMPRESSED_APP",
    8: "WAYPOINT_APP",
    9: "AUDIO_APP",
    10: "DETECTION_SENSOR_APP",
    11: "ALERT_APP",
    12: "KEY_VERIFICATION_APP",
    13: "REMOTE_SHELL_APP",
    32: "REPLY_APP",
    33: "IP_TUNNEL_APP",
    34: "PAXCOUNTER_APP",
    35: "STORE_FORWARD_PLUSPLUS_APP",
    36: "NODE_STATUS_APP",
    37: "MESH_BEACON_APP",
    38: "PAGING_APP",
    64: "SERIAL_APP",
    65: "STORE_FORWARD_APP",
    66: "RANGE_TEST_APP",
    67: "TELEMETRY_APP",
    68: "ZPS_APP",
    69: "SIMULATOR_APP",
    70: "TRACEROUTE_APP",
    71: "NEIGHBORINFO_APP",
    72: "ATAK_PLUGIN",
    73: "MAP_REPORT_APP",
    74: "POWERSTRESS_APP",
    75: "LORAWAN_BRIDGE",
    76: "RETICULUM_TUNNEL_APP",
    77: "CAYENNE_APP",
    78: "ATAK_PLUGIN_V2",
    79: "LORA_OTA_APP",
    112: "GROUPALARM_APP",
    256: "PRIVATE_APP",
    257: "ATAK_FORWARDER",
}


def normalise_portnum(value) -> str:
    """Return the ``PortNum`` name for a port given as a name, an int or a numeric string.

    Lib 2.7.11 sends ports it does not know as integers. An int (or numeric string) maps to its enum name, or to
    ``PORT_<n>`` when the number is not in :data:`PORTNUM_NAMES`. A name passes through unchanged.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return PORTNUM_NAMES.get(value, f"PORT_{value}")
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            number = int(text)
            return PORTNUM_NAMES.get(number, f"PORT_{number}")
        return value
    return str(value)
