"""Queue and link traceroute exploration for active DX events (meshflow-api#221)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from dx_monitoring.models import (
    DxEvent,
    DxEventState,
    DxEventTraceroute,
    DxEventTracerouteOutcome,
    DxEventTracerouteSkipReason,
    DxNodeMetadata,
)
from mesh_monitoring.selection import _distance_km, observed_node_target_coordinates
from nodes.managed_node_liveness import (
    eligible_auto_traceroute_sources_queryset,
    is_managed_node_eligible_traceroute_source,
)
from nodes.models import ManagedNode
from traceroute.dispatch import TRACEROUTE_MAX_PENDING_PER_SOURCE, pending_count_for_source
from traceroute.models import AutoTraceRoute
from traceroute.source_selection import eligible_traceroute_sources_ordered
from traceroute.ws_notify import notify_traceroute_status_changed

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

TRIGGER_SOURCE = "dx_monitoring"


def _recency_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_RECENCY_MINUTES", 120))
    return timedelta(minutes=max(1, m))


def _baseline_recency_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_BASELINE_RECENCY_MINUTES", 120))
    return timedelta(minutes=max(1, m))


def _baseline_failure_cooldown_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_BASELINE_FAILURE_COOLDOWN_MINUTES", 60))
    return timedelta(minutes=max(1, m))


def _source_cooldown_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_SOURCE_COOLDOWN_MINUTES", 30))
    return timedelta(minutes=max(1, m))


def _target_cooldown_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_TARGET_COOLDOWN_MINUTES", 30))
    return timedelta(minutes=max(1, m))


def _event_cooldown_td() -> timedelta:
    m = int(getattr(settings, "DX_MONITORING_EXPLORATION_EVENT_COOLDOWN_MINUTES", 45))
    return timedelta(minutes=max(1, m))


def _max_sources_per_event() -> int:
    return max(1, int(getattr(settings, "DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT", 1)))


def ordered_exploration_sources(event: DxEvent) -> list[ManagedNode]:
    """Prefer ``last_observer`` when eligible, then same-constellation sources by distance, then global order."""
    dest = event.destination
    target_pos = observed_node_target_coordinates(dest)
    target_lat, target_lon = (target_pos[0], target_pos[1]) if target_pos else (None, None)

    seen: set[int] = set()
    out: list[ManagedNode] = []

    lo = event.last_observer
    if lo is not None and is_managed_node_eligible_traceroute_source(lo) and int(lo.node_id) != int(dest.node_id):
        out.append(lo)
        seen.add(lo.pk)

    same_c = list(
        eligible_auto_traceroute_sources_queryset().filter(
            constellation_id=event.constellation_id,
        )
    )
    same_c = [m for m in same_c if m.pk not in seen and int(m.node_id) != int(dest.node_id)]
    same_c.sort(key=lambda mn: (_distance_km(mn, target_lat, target_lon), mn.node_id))
    for m in same_c:
        out.append(m)
        seen.add(m.pk)

    for m in eligible_traceroute_sources_ordered():
        if m.pk in seen:
            continue
        if int(m.node_id) == int(dest.node_id):
            continue
        out.append(m)
        seen.add(m.pk)

    return out


def baseline_row_for_target(target) -> AutoTraceRoute | None:
    """At most one NEW_NODE_BASELINE row exists per target (DB constraint)."""
    return (
        AutoTraceRoute.objects.filter(
            target_node=target,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
        )
        .select_related("source_node")
        .first()
    )


def _baseline_suppresses_dx_for_source(
    baseline: AutoTraceRoute,
    source: ManagedNode,
    now,
) -> tuple[bool, DxEventTracerouteSkipReason | None]:
    """
    When True, do not queue DX_WATCH from this source: baseline already covers or is in flight.

    Returns (suppress, skip_reason_if_suppressed).
    """
    if int(baseline.source_node_id) != int(source.pk):
        return False, None

    if baseline.status in (AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT):
        return True, DxEventTracerouteSkipReason.BASELINE_IN_FLIGHT

    if baseline.status == AutoTraceRoute.STATUS_COMPLETED:
        rec = _baseline_recency_td()
        if baseline.completed_at and now - baseline.completed_at <= rec:
            return True, DxEventTracerouteSkipReason.BASELINE_RECENT_SUCCESS
        return False, None

    if baseline.status == AutoTraceRoute.STATUS_FAILED:
        cool = _baseline_failure_cooldown_td()
        if baseline.completed_at and now - baseline.completed_at < cool:
            return True, DxEventTracerouteSkipReason.BASELINE_FAILURE_COOLDOWN
        return False, None

    return False, None


def _recent_dx_watch_blocks(source: ManagedNode, target, now) -> bool:
    rec = _recency_td()
    fail_cool = _baseline_failure_cooldown_td()
    qs = AutoTraceRoute.objects.filter(
        source_node=source,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
        trigger_source=TRIGGER_SOURCE,
    ).order_by("-triggered_at")[:8]
    for tr in qs:
        if tr.status in (AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT):
            return True
        if tr.status == AutoTraceRoute.STATUS_COMPLETED and tr.completed_at and now - tr.completed_at <= rec:
            return True
        if tr.status == AutoTraceRoute.STATUS_FAILED and tr.completed_at and now - tr.completed_at <= fail_cool:
            return True
    return False


def _source_exploration_spacing_ok(source: ManagedNode, now) -> bool:
    cool = _source_cooldown_td()
    latest = (
        AutoTraceRoute.objects.filter(
            source_node=source,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
            trigger_source=TRIGGER_SOURCE,
        )
        .order_by("-triggered_at")
        .values_list("triggered_at", flat=True)
        .first()
    )
    if latest is None:
        return True
    return latest <= now - cool


def _target_exploration_spacing_ok(target, now) -> bool:
    cool = _target_cooldown_td()
    latest = (
        AutoTraceRoute.objects.filter(
            target_node=target,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
            trigger_source=TRIGGER_SOURCE,
        )
        .order_by("-triggered_at")
        .values_list("triggered_at", flat=True)
        .first()
    )
    if latest is None:
        return True
    return latest <= now - cool


def _fanout_source_ids(event: DxEvent) -> set[int]:
    """Sources already covered by a pending in-flight or completed exploration row for this event."""
    out: set[int] = set()
    for et in DxEventTraceroute.objects.filter(event=event).select_related("auto_traceroute"):
        if et.outcome == DxEventTracerouteOutcome.SKIPPED:
            continue
        if et.outcome == DxEventTracerouteOutcome.FAILED:
            continue
        if et.source_node_id is None:
            continue
        if et.outcome == DxEventTracerouteOutcome.COMPLETED:
            out.add(et.source_node_id)
            continue
        if et.outcome == DxEventTracerouteOutcome.PENDING:
            tr = et.auto_traceroute
            if tr is None:
                continue
            if tr.status in (AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT):
                out.add(et.source_node_id)
    return out


def _record_skip(event: DxEvent, reason: DxEventTracerouteSkipReason, source: ManagedNode | None = None) -> None:
    DxEventTraceroute.objects.create(
        event=event,
        auto_traceroute=None,
        source_node=source,
        outcome=DxEventTracerouteOutcome.SKIPPED,
        skip_reason=reason,
        metadata={},
    )


def plan_event_exploration(event: DxEvent) -> dict:
    """
    Select sources, link baseline coverage, or queue ``DX_WATCH`` rows for one DX event.

    Idempotent with respect to fan-out caps and deduplication rules in the product plan.
    """
    summary: dict = {"linked_baseline": 0, "queued_dx_watch": 0, "skipped": 0, "actions": []}
    if not getattr(settings, "DX_MONITORING_EXPLORATION_ENABLED", False):
        return summary

    now = timezone.now()
    max_src = _max_sources_per_event()
    dest = event.destination

    with transaction.atomic():
        event = DxEvent.objects.select_for_update().get(pk=event.pk)
        if event.state != DxEventState.ACTIVE or event.active_until <= now:
            return summary

        if DxNodeMetadata.objects.filter(observed_node=dest, exclude_from_detection=True).exists():
            _record_skip(event, DxEventTracerouteSkipReason.DESTINATION_EXCLUDED)
            summary["skipped"] += 1
            summary["actions"].append("destination_excluded")
            return summary

        fanout = _fanout_source_ids(event)
        if len(fanout) >= max_src:
            _record_skip(event, DxEventTracerouteSkipReason.FANOUT_SATURATED)
            summary["skipped"] += 1
            summary["actions"].append("fanout_saturated")
            return summary

        sources = ordered_exploration_sources(event)
        if not sources:
            _record_skip(event, DxEventTracerouteSkipReason.NO_ELIGIBLE_SOURCE)
            summary["skipped"] += 1
            summary["actions"].append("no_eligible_source")
            return summary

        baseline = baseline_row_for_target(dest)

        for source in sources:
            if len(fanout) >= max_src:
                break
            if source.pk in fanout:
                continue

            if pending_count_for_source(source.pk) >= TRACEROUTE_MAX_PENDING_PER_SOURCE:
                _record_skip(event, DxEventTracerouteSkipReason.SOURCE_QUEUE_FULL, source=source)
                summary["skipped"] += 1
                continue

            if not _source_exploration_spacing_ok(source, now):
                _record_skip(event, DxEventTracerouteSkipReason.SOURCE_COOLDOWN, source=source)
                summary["skipped"] += 1
                continue

            if baseline is not None:
                suppress, skip_reason = _baseline_suppresses_dx_for_source(baseline, source, now)
                if suppress and skip_reason is not None:
                    if baseline.status == AutoTraceRoute.STATUS_COMPLETED and skip_reason in (
                        DxEventTracerouteSkipReason.BASELINE_RECENT_SUCCESS,
                    ):
                        DxEventTraceroute.objects.create(
                            event=event,
                            auto_traceroute=baseline,
                            source_node=baseline.source_node,
                            outcome=DxEventTracerouteOutcome.COMPLETED,
                            metadata={
                                "link_kind": "new_node_baseline",
                                "route_hops": len(baseline.route or []),
                            },
                        )
                        fanout.add(source.pk)
                        summary["linked_baseline"] += 1
                        summary["actions"].append("linked_baseline_completed")
                        continue
                    if (
                        baseline.status
                        in (
                            AutoTraceRoute.STATUS_PENDING,
                            AutoTraceRoute.STATUS_SENT,
                        )
                        and skip_reason == DxEventTracerouteSkipReason.BASELINE_IN_FLIGHT
                    ):
                        DxEventTraceroute.objects.create(
                            event=event,
                            auto_traceroute=baseline,
                            source_node=baseline.source_node,
                            outcome=DxEventTracerouteOutcome.PENDING,
                            metadata={"link_kind": "new_node_baseline"},
                        )
                        fanout.add(source.pk)
                        summary["linked_baseline"] += 1
                        summary["actions"].append("linked_baseline_pending")
                        continue
                    _record_skip(event, skip_reason, source=source)
                    summary["skipped"] += 1
                    continue

            if _recent_dx_watch_blocks(source, dest, now):
                _record_skip(event, DxEventTracerouteSkipReason.DUPLICATE_DX_WATCH, source=source)
                summary["skipped"] += 1
                continue

            if not _target_exploration_spacing_ok(dest, now):
                _record_skip(event, DxEventTracerouteSkipReason.TARGET_COOLDOWN, source=source)
                summary["skipped"] += 1
                continue

            at_now = timezone.now()
            auto_tr = AutoTraceRoute.objects.create(
                source_node=source,
                target_node=dest,
                trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
                triggered_by=None,
                trigger_source=TRIGGER_SOURCE,
                target_strategy=None,
                status=AutoTraceRoute.STATUS_PENDING,
                earliest_send_at=at_now,
            )
            notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_PENDING)
            DxEventTraceroute.objects.create(
                event=event,
                auto_traceroute=auto_tr,
                source_node=source,
                outcome=DxEventTracerouteOutcome.PENDING,
                metadata={"link_kind": "dx_watch"},
            )
            fanout.add(source.pk)
            summary["queued_dx_watch"] += 1
            summary["actions"].append("queued_dx_watch")
            logger.info(
                "dx_exploration: queued DX_WATCH id=%s event=%s %s -> %s",
                auto_tr.id,
                event.id,
                source.node_id_str,
                dest.node_id_str,
            )

    return summary


def active_events_due_for_exploration():
    """Active DX events whose last exploration attempt is outside the event cooldown window."""
    if not getattr(settings, "DX_MONITORING_EXPLORATION_ENABLED", False):
        return DxEvent.objects.none()

    now = timezone.now()
    cool = _event_cooldown_td()
    cutoff = now - cool

    return (
        DxEvent.objects.filter(state=DxEventState.ACTIVE, active_until__gt=now)
        .annotate(last_exploration=Max("traceroute_explorations__created_at"))
        .filter(Q(last_exploration__isnull=True) | Q(last_exploration__lt=cutoff))
    )


def scan_active_dx_events_for_traceroutes(batch_size: int = 50) -> dict:
    """Plan exploration for active events due for a new attempt (invoked from Celery)."""
    if not getattr(settings, "DX_MONITORING_EXPLORATION_ENABLED", False):
        return {"processed": 0, "skipped_disabled": True}

    n = 0
    for event in active_events_due_for_exploration().order_by("-last_observed_at")[:batch_size]:
        plan_event_exploration(event)
        n += 1
    return {"processed": n}


def on_auto_traceroute_exploration_finished(auto_tr: AutoTraceRoute) -> None:
    """
    Mark linked :class:`DxEventTraceroute` rows when an exploration or baseline-linked TR
    reaches a terminal status (``completed`` or ``failed``).
    """
    is_dx_watch_ours = (
        int(auto_tr.trigger_type) == int(AutoTraceRoute.TRIGGER_TYPE_DX_WATCH)
        and auto_tr.trigger_source == TRIGGER_SOURCE
    )
    is_baseline = int(auto_tr.trigger_type) == int(AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE)
    if not is_dx_watch_ours and not is_baseline:
        return

    terminal = {AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED}
    if auto_tr.status not in terminal:
        return

    for et in DxEventTraceroute.objects.filter(auto_traceroute=auto_tr, outcome=DxEventTracerouteOutcome.PENDING):
        if auto_tr.status == AutoTraceRoute.STATUS_COMPLETED:
            meta = dict(et.metadata or {})
            meta["route_hops"] = len(auto_tr.route or [])
            meta["route_back_hops"] = len(auto_tr.route_back or [])
            et.metadata = meta
            et.outcome = DxEventTracerouteOutcome.COMPLETED
        else:
            et.outcome = DxEventTracerouteOutcome.FAILED
        et.save(update_fields=["outcome", "metadata", "updated_at"])


def exploration_links_auto_traceroute_to_destination(auto_tr: AutoTraceRoute, destination_node_id: int) -> bool:
    """True when this TR is tied to a DX exploration row for an event on that destination."""
    dest_id = int(destination_node_id)
    return DxEventTraceroute.objects.filter(
        auto_traceroute=auto_tr,
        event__destination__node_id=dest_id,
    ).exists()
