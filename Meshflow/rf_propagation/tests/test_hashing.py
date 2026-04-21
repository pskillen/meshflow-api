"""Unit tests for the RF render input hash."""

from __future__ import annotations

from types import SimpleNamespace

from rf_propagation.hashing import compute_input_hash


def _profile(**overrides):
    base = dict(
        rf_latitude=55.8610,
        rf_longitude=-4.2510,
        rf_altitude_m=80.0,
        antenna_height_m=6.0,
        antenna_gain_dbi=3.0,
        tx_power_dbm=27.0,
        rf_frequency_mhz=869.525,
        antenna_pattern="omni",
        antenna_azimuth_deg=None,
        antenna_beamwidth_deg=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_hash_is_deterministic():
    profile = _profile()
    assert compute_input_hash(profile, render_version="1") == compute_input_hash(profile, render_version="1")


def test_hash_changes_for_each_field():
    profile = _profile()
    base = compute_input_hash(profile, render_version="1")
    cases = {
        "rf_latitude": 60.0,
        "rf_longitude": -2.0,
        "rf_altitude_m": 200.0,
        "antenna_height_m": 12.0,
        "antenna_gain_dbi": 9.0,
        "tx_power_dbm": 17.0,
        "rf_frequency_mhz": 915.0,
        "antenna_pattern": "directional",
        "antenna_azimuth_deg": 90.0,
        "antenna_beamwidth_deg": 60.0,
    }
    for field, new_value in cases.items():
        mutated = _profile(**{field: new_value})
        assert compute_input_hash(mutated, render_version="1") != base, field


def test_hash_ignores_subpixel_latlng_noise():
    base = compute_input_hash(_profile(), render_version="1")
    jitter = compute_input_hash(
        _profile(rf_latitude=55.8610 + 1e-8, rf_longitude=-4.2510 - 1e-8),
        render_version="1",
    )
    assert base == jitter


def test_hash_changes_when_render_version_bumps():
    profile = _profile()
    a = compute_input_hash(profile, render_version="1")
    b = compute_input_hash(profile, render_version="2")
    assert a != b


def test_hash_accepts_extras():
    profile = _profile()
    a = compute_input_hash(profile, render_version="1", extras={"radius_m": 20000})
    b = compute_input_hash(profile, render_version="1", extras={"radius_m": 10000})
    assert a != b


def test_hash_extras_cannot_collide_with_profile_field():
    import pytest

    with pytest.raises(ValueError):
        compute_input_hash(_profile(), render_version="1", extras={"rf_latitude": 0.0})


def _full_extras(**overrides):
    base = {
        "radius_m": 50000,
        "colormap": "plasma",
        "high_resolution": False,
        "min_dbm": -130.0,
        "max_dbm": -50.0,
        "signal_threshold": -110.0,
    }
    base.update(overrides)
    return base


def test_hash_changes_when_extras_colormap_changes():
    profile = _profile()
    a = compute_input_hash(profile, render_version="1", extras=_full_extras(colormap="plasma"))
    b = compute_input_hash(profile, render_version="1", extras=_full_extras(colormap="viridis"))
    assert a != b


def test_hash_changes_when_extras_high_resolution_changes():
    profile = _profile()
    a = compute_input_hash(profile, render_version="1", extras=_full_extras(high_resolution=False))
    b = compute_input_hash(profile, render_version="1", extras=_full_extras(high_resolution=True))
    assert a != b


def test_hash_changes_when_extras_signal_threshold_changes():
    profile = _profile()
    a = compute_input_hash(profile, render_version="1", extras=_full_extras(signal_threshold=-110.0))
    b = compute_input_hash(profile, render_version="1", extras=_full_extras(signal_threshold=-115.0))
    assert a != b
