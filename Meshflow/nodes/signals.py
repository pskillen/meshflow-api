"""Signals sent by the nodes app."""

from django.dispatch import Signal

# Sent after a feeder's ``ManagedNode.meshtastic_node_id`` was re-pointed (outcome ``auto_updated`` or ``manual``),
# once the transaction that wrote it has committed. Keyword arguments: ``managed_node``, ``event`` (the
# ``ManagedNodeIdentityEvent``), ``old_node_id``, ``new_node_id``.
feeder_identity_changed = Signal()

# Sent when an ``ObservedNodeIdentityLink`` becomes ``auto`` or ``confirmed`` (created live, or promoted to it), once
# the transaction that wrote it has committed. Keyword argument: ``link``. Nothing consumes it yet; later work that
# carries state across a link listens here. Sent with ``send_robust``: a failing receiver is logged, never raised.
identity_link_live = Signal()
