"""Unit tests for :mod:`rf_propagation.payload`."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from rf_propagation.payload import (
    DEFAULT_COLORMAP,
    DEFAULT_RADIO_CLIMATE,
    InvalidProfileError,
    build_request,
    hash_extras_from_payload,
    normalize_colormap,
)


def _profile(**overrides):
    base = dict(
        rf_latitude=55.861,
        rf_longitude=-4.251,
        rf_altitude_m=80.0,
        antenna_height_m=6.0,
        antenna_gain_dbi=3.0,
        tx_power_dbm=27.0,
        rf_frequency_mhz=869.525,
        antenna_pattern="omni",
        antenna_azimuth_deg=None,
        antenna_beamwidth_deg=None,
        observed_node=SimpleNamespace(node_id=12345),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_request_populates_required_fields():
    payload = build_request(_profile())
    assert payload["lat"] == pytest.approx(55.861)
    assert payload["lon"] == pytest.approx(-4.251)
    assert payload["tx_height"] == pytest.approx(6.0)
    assert payload["tx_gain"] == pytest.approx(3.0)
    assert payload["tx_power"] == pytest.approx(27.0)
    assert payload["frequency_mhz"] == pytest.approx(869.525)
    assert payload["radius"] > 0
    assert payload["colormap"] == DEFAULT_COLORMAP
    assert payload["radio_climate"] == DEFAULT_RADIO_CLIMATE
    # Site Planner's required fields must be present verbatim.
    for required in ("lat", "lon", "tx_power"):
        assert required in payload


def test_build_request_clamps_tx_height_and_gain_below_engine_minimums():
    payload = build_request(_profile(antenna_height_m=0.3, antenna_gain_dbi=-2.0))
    assert payload["tx_height"] == pytest.approx(1.0)
    assert payload["tx_gain"] == pytest.approx(0.0)


def test_build_request_uses_settings_default_radius(settings):
    settings.RF_PROPAGATION_DEFAULT_RADIUS_M = 12345
    payload = build_request(_profile())
    assert payload["radius"] == 12345


def test_build_request_respects_radius_override():
    payload = build_request(_profile(), radius_m=5000)
    assert payload["radius"] == 5000


def test_build_request_rejects_profile_missing_required_field():
    profile = _profile(rf_latitude=None)
    with pytest.raises(InvalidProfileError):
        build_request(profile)


def test_build_request_warns_on_directional_but_still_builds(caplog):
    profile = _profile(antenna_pattern="directional", antenna_azimuth_deg=90.0, antenna_beamwidth_deg=60.0)
    with caplog.at_level(logging.WARNING, logger="rf_propagation.payload"):
        payload = build_request(profile)
    assert any("directional" in rec.getMessage() for rec in caplog.records)
    # We still ask Site Planner for an omni prediction since the engine has no
    # directional model — the profile fields are captured in the hash instead.
    assert payload["tx_gain"] == pytest.approx(3.0)


def test_build_request_falls_back_to_altitude_for_height():
    profile = _profile(antenna_height_m=None, rf_altitude_m=50.0)
    payload = build_request(profile)
    assert payload["tx_height"] == pytest.approx(50.0)


def test_build_request_uses_rf_engine_settings(settings):
    settings.RF_PROPAGATION_COLORMAP = "viridis"
    settings.RF_PROPAGATION_HIGH_RESOLUTION = True
    settings.RF_PROPAGATION_MIN_DBM = -120.0
    settings.RF_PROPAGATION_MAX_DBM = -60.0
    settings.RF_PROPAGATION_SIGNAL_THRESHOLD_DBM = -100.0
    payload = build_request(_profile())
    assert payload["colormap"] == "viridis"
    assert payload["high_resolution"] is True
    assert payload["min_dbm"] == pytest.approx(-120.0)
    assert payload["max_dbm"] == pytest.approx(-60.0)
    assert payload["signal_threshold"] == pytest.approx(-100.0)


def test_hash_extras_from_payload_keys():
    payload = build_request(_profile())
    ext = hash_extras_from_payload(payload)
    assert set(ext) == {
        "radius_m",
        "colormap",
        "high_resolution",
        "min_dbm",
        "max_dbm",
        "signal_threshold",
    }


def test_normalize_colormap_unknown(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="rf_propagation.payload"):
        assert normalize_colormap("not-a-real-map-name-xyz") == "plasma"
    assert any("unknown RF_PROPAGATION_COLORMAP" in rec.message for rec in caplog.records)
