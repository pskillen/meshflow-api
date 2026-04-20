"""Content-addressed hashing for RF propagation renders.

The goal is to detect when two render requests share identical RF inputs
(so we can reuse a cached PNG) while tolerating tiny floating-point noise
on float fields. The render pipeline version is part of the hash, so a
bump invalidates every cached render without schema changes.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    from nodes.models import NodeRfProfile

_LATLNG_PRECISION = 6
_METRES_PRECISION = 2
_DB_PRECISION = 1
_FREQ_PRECISION = 3


def _round_or_none(value: Any, ndigits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def _normalized_profile_dict(profile: "NodeRfProfile") -> dict[str, Any]:
    """Return the deterministic field bag we hash over.

    Keeping rounding here (rather than in the DB) means historical rows
    can be rehashed consistently. Field order is irrelevant because we
    dump JSON with ``sort_keys=True`` downstream.
    """

    return {
        "rf_latitude": _round_or_none(profile.rf_latitude, _LATLNG_PRECISION),
        "rf_longitude": _round_or_none(profile.rf_longitude, _LATLNG_PRECISION),
        "rf_altitude_m": _round_or_none(profile.rf_altitude_m, _METRES_PRECISION),
        "antenna_height_m": _round_or_none(profile.antenna_height_m, _METRES_PRECISION),
        "antenna_gain_dbi": _round_or_none(profile.antenna_gain_dbi, _DB_PRECISION),
        "tx_power_dbm": _round_or_none(profile.tx_power_dbm, _DB_PRECISION),
        "rf_frequency_mhz": _round_or_none(profile.rf_frequency_mhz, _FREQ_PRECISION),
        "antenna_pattern": profile.antenna_pattern,
        "antenna_azimuth_deg": _round_or_none(profile.antenna_azimuth_deg, _DB_PRECISION),
        "antenna_beamwidth_deg": _round_or_none(profile.antenna_beamwidth_deg, _DB_PRECISION),
    }


def compute_input_hash(
    profile: "NodeRfProfile",
    *,
    render_version: str | int | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Return a stable SHA256 hex digest over the rounded profile.

    :param profile: The :class:`NodeRfProfile` being rendered.
    :param render_version: Overrides :data:`settings.RF_PROPAGATION_RENDER_VERSION`.
        Exposed for tests.
    :param extras: Optional extra key/value pairs to fold into the hash
        (e.g. radius or colormap overrides). Keys must be JSON-serialisable.
    """

    data = _normalized_profile_dict(profile)
    data["render_version"] = str(
        render_version if render_version is not None else settings.RF_PROPAGATION_RENDER_VERSION
    )
    if extras:
        for key, value in extras.items():
            if key in data:
                raise ValueError(f"extras key collides with profile field: {key}")
            data[key] = value

    blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
