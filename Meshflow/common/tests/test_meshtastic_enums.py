from common.meshtastic_enums import HARDWARE_MODEL_NAMES, PORTNUM_NAMES, normalise_hw_model, normalise_portnum


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


def test_hw_model_int_and_numeric_string_map_to_name():
    assert normalise_hw_model(150) == "THINKNODE_MX"
    assert normalise_hw_model("150") == "THINKNODE_MX"
    assert normalise_hw_model(" 152 ") == "HELTEC_MESH_POCKET_V2"


def test_hw_model_unknown_number_becomes_hw_n():
    assert normalise_hw_model("999") == "HW_999"
    assert normalise_hw_model(999) == "HW_999"


def test_hw_model_renamed_2_7_names_map_to_2_8():
    assert normalise_hw_model("SENSELORA_S3") == "MAKERFABS_RESERVED"
    assert normalise_hw_model("SENSELORA_RP2040") == "MAKERFABS_TRACKER"
    assert normalise_hw_model("TRACKER_T1000_E_PRO") == "MESH_TRACKER_X1"


def test_hw_model_known_and_odd_names_pass_through():
    assert normalise_hw_model("HELTEC_V3") == "HELTEC_V3"
    assert normalise_hw_model("T-Beam") == "T-Beam"


def test_hw_model_blank_and_none_pass_through():
    assert normalise_hw_model("") == ""
    assert normalise_hw_model(None) is None


def test_hw_model_map_has_2_8_additions():
    assert HARDWARE_MODEL_NAMES[255] == "PRIVATE_HW"
    assert HARDWARE_MODEL_NAMES[151] == "NODARA"
    assert len(HARDWARE_MODEL_NAMES) == 154


def test_non_ascii_digits_pass_through_without_raising():
    assert normalise_portnum("²") == "²"
    assert normalise_hw_model("²") == "²"
    assert normalise_hw_model("١٥٠") == "١٥٠"
