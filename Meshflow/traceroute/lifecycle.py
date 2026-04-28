"""Core traceroute queueing and completion helpers (meshflow-api#247 boundary)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils import timezone

from traceroute.models import AutoTraceRoute
from traceroute.ws_notify import notify_traceroute_status_changed

if TYPE_CHECKING:
    from nodes.models import ManagedNode, ObservedNode
    from packets.models import TraceroutePacket


def create_external_inferred_auto_traceroute(
    *,
    source_node: ManagedNode,
    target_node: ObservedNode,
    triggered_at=None,
) -> AutoTraceRoute:
    """
    Create an ``AutoTraceRoute`` row for a traceroute response that did not match a queued row.

    Packet ingestion completes this row immediately after creation (same flow as matched rows).
    """
    if triggered_at is None:
        triggered_at = timezone.now()
    return AutoTraceRoute.objects.create(
        source_node=source_node,
        target_node=target_node,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_EXTERNAL,
        trigger_source=None,
        triggered_by=None,
        triggered_at=triggered_at,
        status=AutoTraceRoute.STATUS_PENDING,
    )


def apply_auto_traceroute_failure(auto_tr: AutoTraceRoute, *, error_message: str) -> None:
    """Persist terminal failure fields (status, ``completed_at``, ``error_message``)."""
    auto_tr.status = AutoTraceRoute.STATUS_FAILED
    auto_tr.completed_at = timezone.now()
    auto_tr.error_message = error_message
    auto_tr.save(update_fields=["status", "completed_at", "error_message"])


def create_pending_auto_traceroute(
    *,
    source_node: ManagedNode,
    target_node: ObservedNode,
    trigger_type: int,
    trigger_source: str | None,
    triggered_by: Any = None,
    target_strategy: str | None = None,
    earliest_send_at=None,
    notify_pending: bool = True,
) -> AutoTraceRoute:
    """
    Create a queued ``AutoTraceRoute`` with shared defaults (status ``pending``).

    Callers keep dedupe, caps, and source selection. Optionally emits the pending WebSocket notification.
    """
    if earliest_send_at is None:
        earliest_send_at = timezone.now()
    auto_tr = AutoTraceRoute.objects.create(
        source_node=source_node,
        target_node=target_node,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        trigger_source=trigger_source,
        target_strategy=target_strategy,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=earliest_send_at,
    )
    if notify_pending:
        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_PENDING)
    return auto_tr


def apply_auto_traceroute_completion(
    auto_tr: AutoTraceRoute,
    *,
    route: list | None,
    route_back: list | None,
    raw_packet: TraceroutePacket | None,
) -> None:
    """Persist terminal success fields for a traceroute response (no product callbacks)."""
    auto_tr.status = AutoTraceRoute.STATUS_COMPLETED
    auto_tr.route = route
    auto_tr.route_back = route_back
    auto_tr.raw_packet = raw_packet
    auto_tr.completed_at = timezone.now()
    auto_tr.error_message = None
    auto_tr.save(
        update_fields=["status", "route", "route_back", "raw_packet", "completed_at", "error_message"],
    )


def schedule_completed_traceroute_neo4j_export(auto_traceroute_id: int) -> None:
    """Enqueue Neo4j edge sync for a completed row (lazy import keeps Celery wiring in one place)."""
    from traceroute.tasks import push_traceroute_to_neo4j

    push_traceroute_to_neo4j.delay(auto_traceroute_id)
