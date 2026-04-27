"""Celery tasks for DX monitoring."""

from celery import shared_task

from dx_monitoring.exploration import scan_active_dx_events_for_traceroutes
from dx_monitoring.notification_service import run_notify_dx_event


@shared_task
def explore_active_dx_events(batch_size: int = 50):
    """Periodically queue or link traceroute exploration for active DX events."""
    return scan_active_dx_events_for_traceroutes(batch_size=batch_size)


@shared_task(ignore_result=True)
def notify_dx_event(event_id: str, category: str):
    """Queue Discord DMs to opt-in users for a DX :class:`~dx_monitoring.models.DxEvent` and category."""
    return run_notify_dx_event(event_id, category)
