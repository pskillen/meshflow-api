"""Core traceroute queueing and completion helpers (meshflow-api#247 boundary)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils import timezone

from traceroute.models import AutoTraceRoute
from traceroute.ws_notify import notify_traceroute_status_changed

if TYPE_CHECKING:
    from nodes.models import ManagedNode, ObservedNode
    from packets.models import TraceroutePacket


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
