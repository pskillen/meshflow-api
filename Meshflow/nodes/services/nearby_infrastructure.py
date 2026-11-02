"""Public "infrastructure nodes near a point" lookup (bounding box prefilter + haversine)."""

import logging
import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from common.geo import haversine_km
from common.protocol import Protocol
from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import ObservedNode, RoleSource

logger = logging.getLogger(__name__)

DEFAULT_RADIUS_KM = 25.0
MIN_RADIUS_KM, MAX_RADIUS_KM = 1.0, 100.0
DEFAULT_LAST_HEARD_DAYS = 30
MIN_LAST_HEARD_DAYS, MAX_LAST_HEARD_DAYS = 1, 365
MAX_RESULTS = 500
CACHE_KEY_PREFIX = "nodes:infra_nearby:v1"

KM_PER_DEGREE_LAT = 111.32


class NearbyParamError(ValueError):
    """Invalid query parameter; the message is returned to the client in a 400."""


@dataclass(frozen=True)
class NearbyParams:
    lat: float
    lon: float
    radius_km: float
    last_heard_within_days: int
    include_client_base: bool


def _parse_float(query_params, name: str, *, required: bool, default=None) -> float:
    raw = query_params.get(name)
    if raw is None or str(raw).strip() == "":
        if required:
            raise NearbyParamError(f"{name} is required")
        return default
    try:
        value = float(raw)
    except ValueError, TypeError:
        raise NearbyParamError(f"{name} must be a number")
    if not math.isfinite(value):
        raise NearbyParamError(f"{name} must be a number")
    return value


def parse_nearby_params(query_params) -> NearbyParams:
    lat = _parse_float(query_params, "lat", required=True)
    lon = _parse_float(query_params, "lon", required=True)
    if not -90.0 <= lat <= 90.0:
        raise NearbyParamError("lat must be between -90 and 90")
    if not -180.0 <= lon <= 180.0:
        raise NearbyParamError("lon must be between -180 and 180")

    radius = _parse_float(query_params, "radius_km", required=False, default=DEFAULT_RADIUS_KM)
    radius = min(max(radius, MIN_RADIUS_KM), MAX_RADIUS_KM)

    raw_days = query_params.get("last_heard_within_days")
    if raw_days is None or str(raw_days).strip() == "":
        days = DEFAULT_LAST_HEARD_DAYS
    else:
        try:
            days = int(raw_days)
        except ValueError, TypeError:
            raise NearbyParamError("last_heard_within_days must be an integer")
    days = min(max(days, MIN_LAST_HEARD_DAYS), MAX_LAST_HEARD_DAYS)

    include_client_base = query_params.get("include_client_base", "false").lower() == "true"

    return NearbyParams(
        lat=round(lat, 3),
        lon=round(lon, 3),
        radius_km=round(radius, 1),
        last_heard_within_days=days,
        include_client_base=include_client_base,
    )


def _bbox_filter(lat: float, lon: float, radius_km: float) -> Q:
    """SQL prefilter on latest_status lat/lon; the exact radius is applied in Python."""
    dlat = radius_km / KM_PER_DEGREE_LAT
    lat_min = max(-90.0, lat - dlat)
    lat_max = min(90.0, lat + dlat)
    q = Q(latest_status__latitude__range=(lat_min, lat_max))

    if abs(lat) + dlat >= 89.0:
        return q

    dlon = radius_km / (KM_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    lon_min = lon - dlon
    lon_max = lon + dlon
    lon_field = "latest_status__longitude"
    if lon_min < -180.0:
        return q & (Q(**{f"{lon_field}__gte": lon_min + 360.0}) | Q(**{f"{lon_field}__lte": lon_max}))
    if lon_max > 180.0:
        return q & (Q(**{f"{lon_field}__gte": lon_min}) | Q(**{f"{lon_field}__lte": lon_max - 360.0}))
    return q & Q(**{f"{lon_field}__range": (lon_min, lon_max)})


def find_nearby_infrastructure(params: NearbyParams, now=None) -> dict:
    """Return ``{"nodes": [(node, distance_km), ...], "meta": {...}}`` nearest first."""
    from common.mesh_node_helpers import observed_node_id_str

    now = now or timezone.now()
    roles = INFRASTRUCTURE_ROLES + ([RoleSource.CLIENT_BASE] if params.include_client_base else [])
    qs = (
        ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC,
            meshtastic_role__in=roles,
            last_heard__isnull=False,
            last_heard__gte=now - timedelta(days=params.last_heard_within_days),
            latest_status__latitude__isnull=False,
            latest_status__longitude__isnull=False,
        )
        .exclude(latest_status__latitude=0, latest_status__longitude=0)
        .filter(_bbox_filter(params.lat, params.lon, params.radius_km))
        .select_related("latest_status")
    )

    rows = []
    for node in qs:
        d = haversine_km(params.lat, params.lon, node.latest_status.latitude, node.latest_status.longitude)
        if d <= params.radius_km:
            rows.append((d, observed_node_id_str(node), node))
    rows.sort(key=lambda r: (r[0], r[1]))

    truncated = len(rows) > MAX_RESULTS
    rows = rows[:MAX_RESULTS]

    return {
        "nodes": [(node, round(d, 2)) for d, _id, node in rows],
        "meta": {
            "lat": params.lat,
            "lon": params.lon,
            "radius_km": params.radius_km,
            "last_heard_within_days": params.last_heard_within_days,
            "count": len(rows),
            "truncated": truncated,
        },
    }


def cache_key(params: NearbyParams) -> str:
    return (
        f"{CACHE_KEY_PREFIX}:{params.lat:.3f}:{params.lon:.3f}:{params.radius_km:.1f}"
        f":{params.last_heard_within_days}:{int(params.include_client_base)}"
    )


def get_nearby_infrastructure_cached(params: NearbyParams) -> dict:
    """Serialized response body (``results`` + ``meta``), cached briefly when enabled."""
    from nodes.serializers import NearbyInfrastructureNodeSerializer

    ttl = settings.NEARBY_INFRASTRUCTURE_CACHE_SECONDS
    key = cache_key(params)
    if ttl > 0:
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            logger.warning("nearby infrastructure cache get failed", exc_info=True)

    found = find_nearby_infrastructure(params)
    results = []
    for node, distance_km in found["nodes"]:
        node._distance_km = distance_km
        results.append(dict(NearbyInfrastructureNodeSerializer(node).data))
    body = {"results": results, "meta": found["meta"]}

    if ttl > 0:
        try:
            cache.set(key, body, ttl)
        except Exception:
            logger.warning("nearby infrastructure cache set failed", exc_info=True)
    return body
