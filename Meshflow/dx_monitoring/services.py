"""DX candidate detection during packet ingestion and from traceroute results."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.geo import haversine_km
from constellations.models import Constellation
from dx_monitoring.exploration import exploration_links_auto_traceroute_to_destination
from dx_monitoring.models import (
    DxEvent,
    DxEventObservation,
    DxEventState,
    DxNodeMetadata,
    DxReasonCode,
)
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode
from packets.models import PacketObservation, RawPacket, TraceroutePacket
from traceroute.models import AutoTraceRoute

if TYPE_CHECKING:
    from packets.services.base import BasePacketService


def is_direct_packet_observation(observation: PacketObservation) -> bool:
    """True when the packet reached the observer without remaining relay hops."""
    if observation.hop_start is None or observation.hop_limit is None:
        return False
    hops_used = int(observation.hop_start) - int(observation.hop_limit)
    return hops_used == 0


def is_node_suppressed_for_dx(node_id: int) -> bool:
    """True when an ObservedNode with this mesh node_id is excluded from DX detection."""
    return DxNodeMetadata.objects.filter(
        observed_node__node_id=node_id,
        exclude_from_detection=True,
    ).exists()


def is_packet_ingest_suppressed(packet: RawPacket, observer: ManagedNode) -> bool:
    """Bidirectional suppression: sender or managed observer/receiver."""
    if is_node_suppressed_for_dx(int(packet.from_int)):
        return True
    if is_node_suppressed_for_dx(int(observer.node_id)):
        return True
    return False


def _cluster_footprint(constellation_id: int) -> list[tuple[float, float]]:
    """Managed-node default locations that define the local cluster footprint."""
    from nodes.models import ManagedNode

    rows = (
        ManagedNode.objects.filter(constellation_id=constellation_id, deleted_at__isnull=True)
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


def _coords_for_mesh_node(node_id: int, source_managed: ManagedNode) -> tuple[float | None, float | None]:
    if int(node_id) == int(source_managed.node_id):
        return _observer_coords(source_managed)
    observed = ObservedNode.objects.filter(node_id=node_id).first()
    if observed is None:
        return None, None
    return _destination_coords(observed)


def _prior_dx_events_exist(constellation_id: int, destination_id) -> bool:
    return DxEvent.objects.filter(constellation_id=constellation_id, destination_id=destination_id).exists()


def _route_entry_node_id(entry: Any) -> int:
    if isinstance(entry, dict):
        return int(entry["node_id"])
    return int(entry)


def _tr_forward_hop_pairs(source_id: int, target_id: int, route: list | None) -> list[tuple[int, int]]:
    route = route or []
    if not route:
        return [(source_id, target_id)]
    pairs: list[tuple[int, int]] = []
    pairs.append((source_id, _route_entry_node_id(route[0])))
    for i in range(len(route) - 1):
        pairs.append((_route_entry_node_id(route[i]), _route_entry_node_id(route[i + 1])))
    pairs.append((_route_entry_node_id(route[-1]), target_id))
    return pairs


def _tr_return_hop_pairs(target_id: int, source_id: int, route_back: list | None) -> list[tuple[int, int]]:
    route_back = route_back or []
    if not route_back:
        return [(target_id, source_id)]
    pairs: list[tuple[int, int]] = []
    pairs.append((target_id, _route_entry_node_id(route_back[0])))
    for i in range(len(route_back) - 1):
        pairs.append((_route_entry_node_id(route_back[i]), _route_entry_node_id(route_back[i + 1])))
    pairs.append((_route_entry_node_id(route_back[-1]), source_id))
    return pairs


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

    if isinstance(packet, TraceroutePacket):
        return

    if not packet.from_int or packet.first_reported_time is None:
        return
    if observer.node_id == packet.from_int:
        return

    if is_packet_ingest_suppressed(packet, observer):
        return

    if not is_direct_packet_observation(observation):
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
                        "hop_start": observation.hop_start,
                        "hop_limit": observation.hop_limit,
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
                    "hop_start": observation.hop_start,
                    "hop_limit": observation.hop_limit,
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
                        "hop_start": observation.hop_start,
                        "hop_limit": observation.hop_limit,
                    },
                    raw_packet=packet,
                    packet_observation=observation,
                )


def maybe_detect_dx_from_completed_traceroute(
    auto_tr: AutoTraceRoute,
    raw_packet: RawPacket,
    packet_observation: PacketObservation,
) -> None:
    """Detect distant consecutive hops from a completed traceroute path."""
    if not getattr(settings, "DX_MONITORING_DETECTION_ENABLED", False):
        return
    if auto_tr.status != AutoTraceRoute.STATUS_COMPLETED:
        return

    source = auto_tr.source_node
    target = auto_tr.target_node
    constellation = source.constellation
    observed_at = auto_tr.completed_at or timezone.now()
    active_minutes = int(getattr(settings, "DX_MONITORING_EVENT_ACTIVE_MINUTES", 60))
    active_extension = timedelta(minutes=active_minutes)
    hop_km = float(getattr(settings, "DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM", 150.0))

    src_id = int(source.node_id)
    tgt_id = int(target.node_id)
    forward = _tr_forward_hop_pairs(src_id, tgt_id, auto_tr.route)
    backward = _tr_return_hop_pairs(tgt_id, src_id, auto_tr.route_back)

    for direction, pairs in (("forward", forward), ("return", backward)):
        for hop_index, (a_id, b_id) in enumerate(pairs):
            if is_node_suppressed_for_dx(a_id) or is_node_suppressed_for_dx(b_id):
                continue
            la, loa = _coords_for_mesh_node(a_id, source)
            lb, lob = _coords_for_mesh_node(b_id, source)
            if la is None or loa is None or lb is None or lob is None:
                continue
            dist = haversine_km(la, loa, lb, lob)
            if dist <= hop_km:
                continue
            dest_node = ObservedNode.objects.filter(node_id=b_id).first()
            if dest_node is None:
                continue
            if exploration_links_auto_traceroute_to_destination(auto_tr, b_id):
                continue
            _get_or_create_active_event(
                constellation=constellation,
                destination=dest_node,
                reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP,
                observer=source,
                observed_at=observed_at,
                distance_km=dist,
                active_extension=active_extension,
                evidence_metadata={
                    "auto_traceroute_id": str(auto_tr.pk),
                    "path_direction": direction,
                    "hop_index": hop_index,
                    "from_node_id": a_id,
                    "to_node_id": b_id,
                    "distance_km": dist,
                    "threshold_km": hop_km,
                },
                raw_packet=raw_packet,
                packet_observation=packet_observation,
            )
