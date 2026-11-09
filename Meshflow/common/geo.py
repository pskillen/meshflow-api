"""Geographic helpers (no Django models)."""

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    r_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_earth_km * c


NULL_ISLAND_EPSILON = 1e-7


def is_null_island(lat, lon) -> bool:
    """True when both coordinates are present and within 1e-7 of 0 (a "no fix" 0,0 position)."""
    if lat is None or lon is None:
        return False
    return abs(lat) < NULL_ISLAND_EPSILON and abs(lon) < NULL_ISLAND_EPSILON
