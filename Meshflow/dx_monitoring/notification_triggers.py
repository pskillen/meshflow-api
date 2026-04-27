"""Schedule DX notification Celery tasks from detection and event lifecycle hooks."""

from __future__ import annotations

from django.conf import settings

from .models import DxNotificationCategory
from .notification_service import reason_code_to_notification_category


def enqueue_dx_event_notification(event_id, category: str) -> None:
    """
    Queue :func:`dx_monitoring.tasks.notify_dx_event` when the feature flag is on.
    """
    if not getattr(settings, "DX_MONITORING_NOTIFICATIONS_ENABLED", False):
        return
    from .tasks import notify_dx_event  # local import: Celery / task registration

    notify_dx_event.delay(str(event_id), category)


def maybe_enqueue_for_new_reason_event(*, event_id, reason_code: str) -> None:
    """After a *new* DX event row is created, notify for the reason category if applicable."""
    cat = reason_code_to_notification_category(reason_code)
    if cat is None:
        return
    enqueue_dx_event_notification(event_id, cat)


def maybe_enqueue_confirmed_event(*, event_id, observation_count: int) -> None:
    """When observation count reaches the configured threshold, send ``confirmed_event`` if enabled."""
    n = int(getattr(settings, "DX_MONITORING_NOTIFICATION_CONFIRMED_MIN_OBSERVATIONS", 3) or 3)
    if n < 2:
        return
    if observation_count != n:
        return
    enqueue_dx_event_notification(str(event_id), DxNotificationCategory.CONFIRMED_EVENT)


def maybe_enqueue_event_closed(*, event_id) -> None:
    enqueue_dx_event_notification(str(event_id), DxNotificationCategory.EVENT_CLOSED_SUMMARY)
