"""Normalisers for the LoRa region and modem preset the bot reports."""

import pytest

from common.meshtastic_enums import normalise_modem_preset, normalise_region


@pytest.mark.parametrize(
    "value, expected",
    [
        ("EU_868", "EU_868"),
        (3, "EU_868"),
        ("3", "EU_868"),
        (0, "UNSET"),
        ("UNKNOWN_37", "ITU2_125CM"),
        ("UNKNOWN_99", "REGION_99"),
        (99, "REGION_99"),
        ("NEW_FUTURE_REGION", "NEW_FUTURE_REGION"),
        ("  US  ", "US"),
        ("", None),
        ("   ", None),
        (None, None),
        (True, None),
        ("x" * 33, None),
        ("bad\nvalue", None),
        ("9" * 12, None),
        (3.5, None),
    ],
)
def test_normalise_region(value, expected):
    assert normalise_region(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("LONG_FAST", "LONG_FAST"),
        (9, "LONG_TURBO"),
        ("16", "MEDIUM_TURBO"),
        ("UNKNOWN_14", "TINY_FAST"),
        ("UNKNOWN_99", "MODEM_PRESET_99"),
        (99, "MODEM_PRESET_99"),
        ("NEW_FUTURE_PRESET", "NEW_FUTURE_PRESET"),
        ("", None),
        (None, None),
        ("x" * 33, None),
        ("bad\x00value", None),
    ],
)
def test_normalise_modem_preset(value, expected):
    assert normalise_modem_preset(value) == expected
