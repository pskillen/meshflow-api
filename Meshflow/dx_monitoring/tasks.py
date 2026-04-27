"""Celery tasks for DX monitoring."""

from celery import shared_task

from dx_monitoring.exploration import scan_active_dx_events_for_traceroutes


@shared_task
def explore_active_dx_events(batch_size: int = 50):
    """Periodically queue or link traceroute exploration for active DX events."""
    return scan_active_dx_events_for_traceroutes(batch_size=batch_size)
