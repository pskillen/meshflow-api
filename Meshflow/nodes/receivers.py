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
