"""Celery tasks for traceroute scheduling."""

import logging
import random

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from nodes.models import ManagedNode

from .models import AutoTraceRoute
from .target_selection import pick_traceroute_target

logger = logging.getLogger(__name__)


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
