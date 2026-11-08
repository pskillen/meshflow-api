from common.meshtastic_enums import PORTNUM_NAMES, normalise_portnum


def test_name_passes_through():
    assert normalise_portnum("STORE_FORWARD_APP") == "STORE_FORWARD_APP"
    assert normalise_portnum("TEXT_MESSAGE_APP") == "TEXT_MESSAGE_APP"


def test_int_maps_to_name():
    assert normalise_portnum(1) == "TEXT_MESSAGE_APP"
    assert normalise_portnum(38) == "PAGING_APP"
    assert normalise_portnum(37) == "MESH_BEACON_APP"
    assert normalise_portnum(79) == "LORA_OTA_APP"


def test_numeric_string_maps_to_name():
    assert normalise_portnum("38") == "PAGING_APP"
    assert normalise_portnum(" 67 ") == "TELEMETRY_APP"


def test_unknown_number_becomes_port_n():
    assert normalise_portnum(999) == "PORT_999"
    assert normalise_portnum("999") == "PORT_999"


def test_unknown_name_passes_through():
    assert normalise_portnum("PORT_999") == "PORT_999"
    assert normalise_portnum("SOME_NEW_APP") == "SOME_NEW_APP"


def test_map_has_known_ports():
    assert PORTNUM_NAMES[65] == "STORE_FORWARD_APP"
    assert PORTNUM_NAMES[5] == "ROUTING_APP"
    assert PORTNUM_NAMES[70] == "TRACEROUTE_APP"
