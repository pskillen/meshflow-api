"""Centre+radius to WGS84 bbox.

Site Planner / SPLAT! outputs GeoTIFFs already in EPSG:4326, so we do not
reproject — we only need the axis-aligned lat/lng bounding box that the
Leaflet ``imageOverlay`` expects as ``[[south, west], [north, east]]``.

The maths uses the standard small-distance approximation:

.. math::

   \\Delta\\mathrm{lat} = \\frac{r}{111{,}320\\,\\mathrm{m/deg}}

   \\Delta\\mathrm{lng} = \\frac{r}{111{,}320 \\cdot \\cos(\\mathrm{lat})}

This is accurate to well within a PNG pixel at the ≤20 km radii we use,
which is the whole point of keeping this cheap and dependency-free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METRES_PER_DEGREE_LATITUDE = 111_320.0


@dataclass(frozen=True)
class Bbox:
    """Axis-aligned WGS84 bounding box (degrees)."""

    west: float
    south: float
    east: float
    north: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)


def bbox_from_center(lat: float, lng: float, radius_m: float) -> Bbox:
    """Return the WGS84 bbox centred on (``lat``, ``lng``) of radius ``radius_m``.

    Clamps ``cos(lat)`` to avoid a zero divisor exactly at the poles; a caller
    rendering at the pole has bigger problems than a slightly off east/west
    edge, so we just guard the maths.
    """

    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat out of range: {lat}")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"lng out of range: {lng}")

    d_lat = radius_m / METRES_PER_DEGREE_LATITUDE
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    d_lng = radius_m / (METRES_PER_DEGREE_LATITUDE * cos_lat)

    return Bbox(
        west=lng - d_lng,
        south=lat - d_lat,
        east=lng + d_lng,
        north=lat + d_lat,
    )
