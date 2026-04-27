"""Model signals for DX notification lifecycle (e.g. event closed)."""

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import DxEvent, DxEventState


@receiver(pre_save, sender=DxEvent)
def dx_event_store_previous_state_for_notifications(sender, instance, **kwargs):
    if not instance.pk:
        instance._dx_notif_prev_state = None
        return
    try:
        old = DxEvent.objects.get(pk=instance.pk)
        instance._dx_notif_prev_state = old.state
    except DxEvent.DoesNotExist:
        instance._dx_notif_prev_state = None


@receiver(post_save, sender=DxEvent)
def dx_event_notify_on_closed(sender, instance, **kwargs):
    if not getattr(settings, "DX_MONITORING_NOTIFICATIONS_ENABLED", False):
        return
    if instance.state != DxEventState.CLOSED:
        return
    if getattr(instance, "_dx_notif_prev_state", None) == DxEventState.CLOSED:
        return
    from .notification_triggers import maybe_enqueue_event_closed

    maybe_enqueue_event_closed(event_id=instance.pk)
