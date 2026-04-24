"""Celery tasks for the nodes app."""

from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from celery import shared_task

from nodes.managed_node_liveness import schedule_traceroute_source_recency_seconds
from nodes.models import ManagedNode, ManagedNodeStatus
from packets.models import PacketObservation


@shared_task
def update_managed_node_statuses():
    """
    Bulk refresh ManagedNodeStatus from PacketObservation.upload_time.

    is_sending_data uses the same recency window as traceroute feeder eligibility
    (SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS).
    """
    now = timezone.now()
    cutoff = now - timedelta(seconds=schedule_traceroute_source_recency_seconds())

    last_by_observer = dict(
        PacketObservation.objects.values("observer_id").annotate(m=Max("upload_time")).values_list("observer_id", "m")
    )

    existing = {s.node_id: s for s in ManagedNodeStatus.objects.all()}
    to_create = []
    to_update = []
    sending_count = 0

    for mn in ManagedNode.objects.all().only("pk"):
        last = last_by_observer.get(mn.pk)
        is_sending = last is not None and last >= cutoff
        if is_sending:
            sending_count += 1

        st = existing.get(mn.pk)
        if st is None:
            to_create.append(
                ManagedNodeStatus(
                    node=mn,
                    last_packet_ingested_at=last,
                    is_sending_data=is_sending,
                )
            )
        elif st.last_packet_ingested_at != last or st.is_sending_data != is_sending:
            st.last_packet_ingested_at = last
            st.is_sending_data = is_sending
            to_update.append(st)

    created = len(to_create)
    updated = len(to_update)

    if to_create:
        ManagedNodeStatus.objects.bulk_create(to_create, batch_size=500)
    if to_update:
        ManagedNodeStatus.objects.bulk_update(
            to_update,
            ["last_packet_ingested_at", "is_sending_data"],
            batch_size=500,
        )
        ManagedNodeStatus.objects.filter(node_id__in=[s.node_id for s in to_update]).update(updated_at=now)

    return {
        "created": created,
        "updated": updated,
        "sending": sending_count,
    }
