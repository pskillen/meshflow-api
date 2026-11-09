"""Signals sent by the nodes app."""

from django.dispatch import Signal

# Sent after a feeder's ``ManagedNode.meshtastic_node_id`` was re-pointed (outcome ``auto_updated`` or ``manual``),
# once the transaction that wrote it has committed. Keyword arguments: ``managed_node``, ``event`` (the
# ``ManagedNodeIdentityEvent``), ``old_node_id``, ``new_node_id``.
feeder_identity_changed = Signal()
