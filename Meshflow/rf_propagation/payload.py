"""Build Site Planner ``CoveragePredictionRequest`` payloads from an RF profile.

Site Planner's current request schema does not model directional antennas,
so we always submit an omni prediction and surface a note on the render
(and a WARN log) when the operator has picked ``directional``. This matches
the v1 feature intent (rough coverage maps, not calibrated RF engineering).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    from nodes.models import NodeRfProfile

logger = logging.getLogger(__name__)

DEFAULT_RX_HEIGHT_M = 1.0
DEFAULT_RX_GAIN_DBI = 1.0
# Deprecated: use ``settings.RF_PROPAGATION_*`` for tunable defaults (see below).
DEFAULT_SIGNAL_THRESHOLD_DBM = -110.0
DEFAULT_RADIO_CLIMATE = "maritime_temperate_land"
DEFAULT_COLORMAP = "plasma"
DEFAULT_MIN_DBM = -130.0
DEFAULT_MAX_DBM = -50.0
DEFAULT_HIGH_RESOLUTION = False

_MISSING = object()

# Names accepted by matplotlib / Site Planner colormap lookup (lowercase).
_ALLOWED_MATPLOTLIB_COLORMAPS = frozenset(
    {
        "viridis",
        "plasma",
        "inferno",
        "magma",
        "cividis",
        "turbo",
        "jet",
        "terrain",
        "gist_earth",
        "ocean",
        "gist_ncar",
        "coolwarm",
        "rdylgn",
        "spectral",
        "rainbow",
        "gist_rainbow",
        "hot",
        "afmhot",
        "spring",
        "summer",
        "autumn",
        "winter",
        "bone",
        "copper",
        "pink",
        "gray",
        "grey",
        "binary",
        "cool",
        "hsv",
        "gnuplot",
        "gnuplot2",
        "cmrmap",
        "brg",
        "nipy_spectral",
        "gist_stern",
        "prism",
        "tab10",
        "tab20",
        "set1",
        "set2",
        "set3",
    }
)


class InvalidProfileError(ValueError):
    """Raised when a profile is missing fields required to call the engine."""


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise InvalidProfileError(f"RF profile is missing required field: {name}")
    return value


def normalize_colormap(name: str) -> str:
    """Return a matplotlib colormap name safe to send to Site Planner.

    Unknown values log a warning and fall back to ``plasma``.
    """

    key = str(name).strip().lower()
    if key in _ALLOWED_MATPLOTLIB_COLORMAPS:
        return key
    logger.warning(
        "rf_propagation.payload: unknown RF_PROPAGATION_COLORMAP=%r; using plasma",
        name,
    )
    return "plasma"


def hash_extras_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonical keys folded into :func:`rf_propagation.hashing.compute_input_hash`."""

    return {
        "radius_m": int(payload["radius"]),
        "colormap": str(payload["colormap"]),
        "high_resolution": bool(payload["high_resolution"]),
        "min_dbm": round(float(payload["min_dbm"]), 1),
        "max_dbm": round(float(payload["max_dbm"]), 1),
        "signal_threshold": round(float(payload["signal_threshold"]), 1),
    }


def build_request(profile: "NodeRfProfile", *, radius_m: int | None = None) -> dict[str, Any]:
    """Return a dict suitable for ``POST /predict`` on Site Planner.

    Raises :class:`InvalidProfileError` when the profile lacks any of the
    required latitude/longitude/frequency/tx-power fields.
    """

    if radius_m is None:
        radius_m = settings.RF_PROPAGATION_DEFAULT_RADIUS_M

    lat = _require(profile.rf_latitude, "rf_latitude")
    lng = _require(profile.rf_longitude, "rf_longitude")
    freq = _require(profile.rf_frequency_mhz, "rf_frequency_mhz")
    tx_power = _require(profile.tx_power_dbm, "tx_power_dbm")

    tx_height_raw = (
        profile.antenna_height_m
        if profile.antenna_height_m is not None
        else (profile.rf_altitude_m if profile.rf_altitude_m is not None else 1.0)
    )
    # Site Planner enforces tx_height >= 1 m and tx_gain >= 0 dBi; clamp defensively
    # so realistic-but-low Meshtastic profiles still produce a render.
    tx_height = max(1.0, float(tx_height_raw))
    tx_gain_raw = profile.antenna_gain_dbi if profile.antenna_gain_dbi is not None else 0.0
    tx_gain = max(0.0, float(tx_gain_raw))

    if profile.antenna_pattern == "directional":
        logger.warning(
            "rf_propagation.payload: directional antenna requested for node_id=%s; "
            "Site Planner only supports omni — rendering omni",
            getattr(profile.observed_node, "node_id", "?"),
        )

    colormap = normalize_colormap(getattr(settings, "RF_PROPAGATION_COLORMAP", DEFAULT_COLORMAP))
    high_res = bool(getattr(settings, "RF_PROPAGATION_HIGH_RESOLUTION", DEFAULT_HIGH_RESOLUTION))
    min_dbm = float(getattr(settings, "RF_PROPAGATION_MIN_DBM", DEFAULT_MIN_DBM))
    max_dbm = float(getattr(settings, "RF_PROPAGATION_MAX_DBM", DEFAULT_MAX_DBM))
    signal_threshold = float(getattr(settings, "RF_PROPAGATION_SIGNAL_THRESHOLD_DBM", DEFAULT_SIGNAL_THRESHOLD_DBM))

    payload: dict[str, Any] = {
        "lat": float(lat),
        "lon": float(lng),
        "tx_height": tx_height,
        "tx_gain": tx_gain,
        "tx_power": float(tx_power),
        "frequency_mhz": float(freq),
        "rx_height": DEFAULT_RX_HEIGHT_M,
        "rx_gain": DEFAULT_RX_GAIN_DBI,
        "signal_threshold": signal_threshold,
        "radio_climate": DEFAULT_RADIO_CLIMATE,
        "colormap": colormap,
        "radius": int(radius_m),
        "min_dbm": min_dbm,
        "max_dbm": max_dbm,
        "high_resolution": high_res,
    }
    return payload
