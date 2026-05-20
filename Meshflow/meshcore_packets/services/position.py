"""MeshCore ADVERT position ingest into canonical Position / NodeLatestStatus models."""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

from meshcore_packets.models import MeshCoreRawPacket
from nodes.models import MeshCoreLocationSource, NodeLatestStatus, ObservedNode, Position


def extract_adv_coords(raw: dict) -> tuple[float, float] | None:
    """Return (lat, lon) from ingest ``raw_json`` when position is present.

    ``0.0`` for both coordinates means absent per ADR-0001 / capture docs.
    """
    if not raw:
        return None
    adv_lat = raw.get("adv_lat")
    adv_lon = raw.get("adv_lon")
    if adv_lat is None or adv_lon is None:
        return None
    lat = float(adv_lat)
    lon = float(adv_lon)
    if lat == 0.0 and lon == 0.0:
        return None
    return lat, lon


def adv_timestamp_to_aware(raw: dict) -> datetime | None:
    """Convert ``adv_timestamp`` (Unix seconds) from ingest envelope to aware datetime."""
    ts = raw.get("adv_timestamp") if raw else None
    if ts is None:
        return None
    try:
        value = float(ts)
    except TypeError, ValueError:
        return None
    reported = datetime.fromtimestamp(value, tz=dt_timezone.utc)
    if timezone.is_naive(reported):
        return timezone.make_aware(reported)
    return reported


def apply_advert_position(*, node: ObservedNode, packet: MeshCoreRawPacket, raw: dict | None) -> bool:
    """Create ``Position`` history and update ``NodeLatestStatus`` from an ADVERT packet.

    Returns True when coordinates were applied; False when position was absent.
    """
    coords = extract_adv_coords(raw or {})
    if coords is None:
        return False

    lat, lon = coords
    reported_time = adv_timestamp_to_aware(raw or {}) or packet.rx_time

    Position.objects.create(
        node=node,
        reported_time=reported_time,
        latitude=lat,
        longitude=lon,
        meshcore_location_source=MeshCoreLocationSource.ADVERT,
        original_mc_packet=packet,
    )
    NodeLatestStatus.objects.update_or_create(
        node=node,
        defaults={
            "latitude": lat,
            "longitude": lon,
            "meshcore_location_source": MeshCoreLocationSource.ADVERT,
            "position_reported_time": reported_time,
        },
    )
    return True
