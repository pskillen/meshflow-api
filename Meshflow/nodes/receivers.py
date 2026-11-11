"""Signal receivers for the nodes app."""

import logging

from django.dispatch import receiver

from nodes.signals import feeder_identity_changed

logger = logging.getLogger(__name__)


@receiver(feeder_identity_changed, dispatch_uid="nodes.feeder_identity_notify_owner")
def notify_owner_of_feeder_identity_change(sender, managed_node=None, event=None, **kwargs):
    """Queue a DM to the feeder's owner when its number was re-pointed automatically (never raises)."""
    from nodes.models import ManagedNodeIdentityEvent
    from nodes.services.feeder_identity_notify import queue_owner_notification

    if event is None or event.outcome != ManagedNodeIdentityEvent.Outcome.AUTO_UPDATED:
        return
    queue_owner_notification(event)


@receiver(feeder_identity_changed, dispatch_uid="nodes.feeder_identity_link_rows")
def link_rows_of_rekeyed_feeder(sender, managed_node=None, event=None, old_node_id=None, new_node_id=None, **kwargs):
    """Record the feeder's old and new ObservedNode rows as one identity link (never raises).

    ``repoint_feeder`` sends this signal with plain ``send``, so an exception here would turn a committed manual
    re-point into a 500: everything is caught inside ``detect_after_feeder_rekey``, and this wrapper too.
    """
    try:
        from nodes.models import ManagedNodeIdentityEvent
        from nodes.services.identity_links import detect_after_feeder_rekey

        if event is None or old_node_id is None or new_node_id is None:
            return
        manual = event.outcome == ManagedNodeIdentityEvent.Outcome.MANUAL
        detect_after_feeder_rekey(
            old_node_id,
            new_node_id,
            manual=manual,
            reviewer=event.acknowledged_by if manual else None,
            event_id=event.pk,
        )
    except Exception:
        logger.exception("Identity link receiver failed for feeder re-key %s -> %s", old_node_id, new_node_id)
