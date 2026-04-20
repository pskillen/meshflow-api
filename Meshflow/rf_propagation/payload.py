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
DEFAULT_SIGNAL_THRESHOLD_DBM = -110.0
DEFAULT_RADIO_CLIMATE = "maritime_temperate_land"
DEFAULT_COLORMAP = "viridis"
DEFAULT_MIN_DBM = -130.0
DEFAULT_MAX_DBM = -50.0
DEFAULT_HIGH_RESOLUTION = False

_MISSING = object()


class InvalidProfileError(ValueError):
    """Raised when a profile is missing fields required to call the engine."""


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise InvalidProfileError(f"RF profile is missing required field: {name}")
    return value


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

    tx_height = (
        profile.antenna_height_m
        if profile.antenna_height_m is not None
        else (profile.rf_altitude_m if profile.rf_altitude_m is not None else 1.0)
    )
    tx_gain = profile.antenna_gain_dbi if profile.antenna_gain_dbi is not None else 0.0

    if profile.antenna_pattern == "directional":
        logger.warning(
            "rf_propagation.payload: directional antenna requested for node_id=%s; "
            "Site Planner only supports omni — rendering omni",
            getattr(profile.observed_node, "node_id", "?"),
        )

    payload: dict[str, Any] = {
        "tx_lat": float(lat),
        "tx_lng": float(lng),
        "tx_height": float(tx_height),
        "tx_gain": float(tx_gain),
        "tx_power": float(tx_power),
        "frequency": float(freq),
        "rx_height": DEFAULT_RX_HEIGHT_M,
        "rx_gain": DEFAULT_RX_GAIN_DBI,
        "signal_threshold": DEFAULT_SIGNAL_THRESHOLD_DBM,
        "radio_climate": DEFAULT_RADIO_CLIMATE,
        "colormap": DEFAULT_COLORMAP,
        "radius": int(radius_m),
        "min_dbm": DEFAULT_MIN_DBM,
        "max_dbm": DEFAULT_MAX_DBM,
        "high_resolution": DEFAULT_HIGH_RESOLUTION,
    }
    return payload
