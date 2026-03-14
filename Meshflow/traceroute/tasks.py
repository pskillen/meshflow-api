"""Celery tasks for traceroute scheduling."""

import logging
import random
from datetime import timedelta

from django.utils import timezone

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from nodes.models import ManagedNode

from .models import AutoTraceRoute
from .target_selection import pick_traceroute_target
from .ws_notify import notify_traceroute_status_changed

logger = logging.getLogger(__name__)

STALE_TR_TIMEOUT_SECONDS = 180


@shared_task
def schedule_traceroutes():
    """
    Run periodically (e.g. every 2h). Pick one random ManagedNode, pick one target,
    create AutoTraceRoute (trigger_type=auto, trigger_source=scheduler),
    send traceroute command via channel layer.
    """
    channel_layer = get_channel_layer()
    managed_nodes = list(ManagedNode.objects.filter(allow_auto_traceroute=True).select_related("constellation"))
    if not managed_nodes:
        return {"created": 0}

    source_node = random.choice(managed_nodes)
    target_node = pick_traceroute_target(source_node)
    if not target_node:
        logger.debug("schedule_traceroutes: no target for node %s", source_node.node_id_str)
        return {"created": 0}

    auto_tr = AutoTraceRoute.objects.create(
        source_node=source_node,
        target_node=target_node,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_AUTO,
        triggered_by=None,
        trigger_source="scheduler",
        status=AutoTraceRoute.STATUS_PENDING,
    )

    async_to_sync(channel_layer.group_send)(
        f"node_{source_node.node_id}",
        {
            "type": "node_command",
            "command": {"type": "traceroute", "target": target_node.node_id},
        },
    )

    auto_tr.status = AutoTraceRoute.STATUS_SENT
    auto_tr.save(update_fields=["status"])
    logger.info(
        "schedule_traceroutes: sent TR %s -> %s (id=%s)",
        source_node.node_id_str,
        target_node.node_id_str,
        auto_tr.id,
    )

    return {"created": 1}


@shared_task
def export_traceroutes_to_neo4j():
    """
    One-off export of all completed AutoTraceRoute records to Neo4j.
    Idempotent; can re-run.
    """
    from .neo4j_service import export_all_traceroutes_to_neo4j

    return export_all_traceroutes_to_neo4j()


@shared_task
def push_traceroute_to_neo4j(auto_traceroute_id: int):
    """
    Push a single completed AutoTraceRoute to Neo4j.
    Called when a traceroute completes (from packet receiver).
    """
    from .neo4j_service import add_traceroute_edges, get_driver

    auto_tr = AutoTraceRoute.objects.filter(pk=auto_traceroute_id).first()
    if not auto_tr or auto_tr.status != AutoTraceRoute.STATUS_COMPLETED:
        logger.debug(
            "push_traceroute_to_neo4j: skipping AutoTraceRoute %s (not completed)",
            auto_traceroute_id,
        )
        return {"skipped": True}

    try:
        driver = get_driver()
        add_traceroute_edges(auto_tr, driver=driver)
        return {"pushed": True}
    except Exception as e:
        logger.exception(
            "push_traceroute_to_neo4j: failed for AutoTraceRoute %s: %s",
            auto_traceroute_id,
            e,
        )
        raise


@shared_task
def mark_stale_traceroutes_failed():
    """
    Run every 60 seconds. Mark traceroutes still pending/sent after 180s as failed.
    Broadcast each update to WebSocket clients.
    """
    cutoff = timezone.now() - timedelta(seconds=STALE_TR_TIMEOUT_SECONDS)
    stale = AutoTraceRoute.objects.filter(
        status__in=[AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT],
        triggered_at__lt=cutoff,
    )
    updated = 0
    for auto_tr in stale:
        auto_tr.status = AutoTraceRoute.STATUS_FAILED
        auto_tr.completed_at = timezone.now()
        auto_tr.error_message = "Timed out after 180s"
        auto_tr.save(update_fields=["status", "completed_at", "error_message"])
        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_FAILED)
        updated += 1
        logger.info(
            "mark_stale_traceroutes_failed: TR id=%s marked failed (timed out)",
            auto_tr.id,
        )
    return {"updated": updated}
