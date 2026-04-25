"""DX candidate detection during packet ingestion."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.geo import haversine_km
from constellations.models import Constellation
from dx_monitoring.models import (
    DxEvent,
    DxEventObservation,
    DxEventState,
    DxNodeMetadata,
    DxReasonCode,
)
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode
from packets.models import PacketObservation, RawPacket

if TYPE_CHECKING:
    from packets.services.base import BasePacketService


def _cluster_footprint(constellation_id: int) -> list[tuple[float, float]]:
    """Managed-node default locations that define the local cluster footprint."""
    from nodes.models import ManagedNode

    rows = (
        ManagedNode.objects.filter(constellation_id=constellation_id)
        .exclude(default_location_latitude__isnull=True)
        .exclude(default_location_longitude__isnull=True)
        .values_list("default_location_latitude", "default_location_longitude")
    )
    return [(float(lat), float(lon)) for lat, lon in rows if lat is not None and lon is not None]


def _min_distance_to_footprint_km(dest_lat: float, dest_lon: float, footprint: list[tuple[float, float]]) -> float:
    return min(haversine_km(dest_lat, dest_lon, lat, lon) for lat, lon in footprint)


def _destination_coords(from_node: ObservedNode) -> tuple[float | None, float | None]:
    status = NodeLatestStatus.objects.filter(node=from_node).first()
    if status is None or status.latitude is None or status.longitude is None:
        return None, None
    return float(status.latitude), float(status.longitude)


def _observer_coords(observer: ManagedNode) -> tuple[float | None, float | None]:
    if observer.default_location_latitude is None or observer.default_location_longitude is None:
        return None, None
    return float(observer.default_location_latitude), float(observer.default_location_longitude)


def _prior_dx_events_exist(constellation_id: int, destination_id) -> bool:
    return DxEvent.objects.filter(constellation_id=constellation_id, destination_id=destination_id).exists()


def _append_observation(
    *,
    event: DxEvent,
    raw_packet: RawPacket,
    packet_observation: PacketObservation,
    observer: ManagedNode,
    observed_at,
    distance_km: float | None,
    metadata: dict[str, Any],
) -> None:
    DxEventObservation.objects.create(
        event=event,
        raw_packet=raw_packet,
        packet_observation=packet_observation,
        observer=observer,
        observed_at=observed_at,
        distance_km=distance_km,
        metadata=metadata,
    )


def _touch_event(
    *,
    event: DxEvent,
    observer: ManagedNode,
    observed_at,
    distance_km: float | None,
    active_extension: timedelta,
) -> None:
    now = timezone.now()
    event.last_observed_at = observed_at
    event.observation_count += 1
    event.last_observer = observer
    if distance_km is not None:
        event.last_distance_km = distance_km
        if event.best_distance_km is None or distance_km > event.best_distance_km:
            event.best_distance_km = distance_km
    new_active_until = max(event.active_until, now + active_extension)
    event.active_until = new_active_until
    event.save(
        update_fields=[
            "last_observed_at",
            "observation_count",
            "last_observer",
            "last_distance_km",
            "best_distance_km",
            "active_until",
        ]
    )


def _get_or_create_active_event(
    *,
    constellation: Constellation,
    destination: ObservedNode,
    reason_code: str,
    observer: ManagedNode,
    observed_at,
    distance_km: float | None,
    active_extension: timedelta,
    evidence_metadata: dict[str, Any],
    raw_packet: RawPacket,
    packet_observation: PacketObservation,
) -> DxEvent:
    now = timezone.now()
    qs = DxEvent.objects.filter(
        constellation=constellation,
        destination=destination,
        reason_code=reason_code,
        active_until__gt=now,
        state=DxEventState.ACTIVE,
    )
    event = qs.first()
    if event:
        _touch_event(
            event=event,
            observer=observer,
            observed_at=observed_at,
            distance_km=distance_km,
            active_extension=active_extension,
        )
        _append_observation(
            event=event,
            raw_packet=raw_packet,
            packet_observation=packet_observation,
            observer=observer,
            observed_at=observed_at,
            distance_km=distance_km,
            metadata=evidence_metadata,
        )
        return event

    active_until = now + active_extension
    event = DxEvent.objects.create(
        constellation=constellation,
        destination=destination,
        reason_code=reason_code,
        state=DxEventState.ACTIVE,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        active_until=active_until,
        observation_count=1,
        last_observer=observer,
        best_distance_km=distance_km,
        last_distance_km=distance_km,
        metadata={},
    )
    _append_observation(
        event=event,
        raw_packet=raw_packet,
        packet_observation=packet_observation,
        observer=observer,
        observed_at=observed_at,
        distance_km=distance_km,
        metadata=evidence_metadata,
    )
    return event


def maybe_detect_dx_candidate(packet_service: BasePacketService) -> None:
    """Run DX rules after packet-specific processing, before ``last_heard`` update."""
    if not getattr(settings, "DX_MONITORING_DETECTION_ENABLED", False):
        return

    packet: RawPacket = packet_service.packet
    observer: ManagedNode = packet_service.observer
    observation: PacketObservation = packet_service.observation
    from_node: ObservedNode = packet_service.from_node

    if not packet.from_int or packet.first_reported_time is None:
        return
    if observer.node_id == packet.from_int:
        return

    constellation = observer.constellation
    observed_at = packet.first_reported_time
    active_minutes = int(getattr(settings, "DX_MONITORING_EVENT_ACTIVE_MINUTES", 60))
    active_extension = timedelta(minutes=active_minutes)
    cluster_km = float(getattr(settings, "DX_MONITORING_CLUSTER_DISTANCE_KM", 150.0))
    direct_km = float(getattr(settings, "DX_MONITORING_DIRECT_DISTANCE_KM", 100.0))
    quiet_days = int(getattr(settings, "DX_MONITORING_RETURNED_DX_QUIET_DAYS", 30))

    prior_dx = _prior_dx_events_exist(constellation.id, from_node.pk)
    previous_last_heard = getattr(packet_service, "_dx_previous_last_heard", None)

    dest_lat, dest_lon = _destination_coords(from_node)
    obs_lat, obs_lon = _observer_coords(observer)
    footprint = _cluster_footprint(constellation.id)

    meta, _ = DxNodeMetadata.objects.get_or_create(observed_node=from_node)
    if meta.exclude_from_detection:
        return

    with transaction.atomic():
        meta = DxNodeMetadata.objects.select_for_update().get(pk=meta.pk)
        if meta.exclude_from_detection:
            return

        if dest_lat is not None and dest_lon is not None and footprint:
            min_cluster_km = _min_distance_to_footprint_km(dest_lat, dest_lon, footprint)
            if not meta.cluster_position_evaluated_for_dx:
                meta.cluster_position_evaluated_for_dx = True
                meta.save(update_fields=["cluster_position_evaluated_for_dx", "updated_at"])
            if min_cluster_km > cluster_km:
                _get_or_create_active_event(
                    constellation=constellation,
                    destination=from_node,
                    reason_code=DxReasonCode.NEW_DISTANT_NODE,
                    observer=observer,
                    observed_at=observed_at,
                    distance_km=min_cluster_km,
                    active_extension=active_extension,
                    evidence_metadata={
                        "min_cluster_distance_km": min_cluster_km,
                        "cluster_threshold_km": cluster_km,
                    },
                    raw_packet=packet,
                    packet_observation=observation,
                )

        if (
            dest_lat is not None
            and dest_lon is not None
            and prior_dx
            and previous_last_heard is not None
            and (observed_at - previous_last_heard) >= timedelta(days=quiet_days)
        ):
            gap_seconds = (observed_at - previous_last_heard).total_seconds()
            _get_or_create_active_event(
                constellation=constellation,
                destination=from_node,
                reason_code=DxReasonCode.RETURNED_DX_NODE,
                observer=observer,
                observed_at=observed_at,
                distance_km=None,
                active_extension=active_extension,
                evidence_metadata={
                    "quiet_days": quiet_days,
                    "gap_seconds": gap_seconds,
                },
                raw_packet=packet,
                packet_observation=observation,
            )

        if dest_lat is not None and dest_lon is not None and obs_lat is not None and obs_lon is not None:
            direct_dist = haversine_km(obs_lat, obs_lon, dest_lat, dest_lon)
            if direct_dist > direct_km:
                _get_or_create_active_event(
                    constellation=constellation,
                    destination=from_node,
                    reason_code=DxReasonCode.DISTANT_OBSERVATION,
                    observer=observer,
                    observed_at=observed_at,
                    distance_km=direct_dist,
                    active_extension=active_extension,
                    evidence_metadata={
                        "direct_distance_km": direct_dist,
                        "direct_threshold_km": direct_km,
                    },
                    raw_packet=packet,
                    packet_observation=observation,
                )
