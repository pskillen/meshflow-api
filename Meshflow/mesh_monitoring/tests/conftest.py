"""Shared helpers for mesh_monitoring tests."""

from mesh_monitoring.models import NodePresence, NodeWatch


def create_watch_with_offline_threshold(*, user, observed_node, offline_after=60, enabled=True):
    """Create an enabled NodeWatch and set the node-level silence threshold on NodePresence."""
    watch = NodeWatch.objects.create(user=user, observed_node=observed_node, enabled=enabled)
    NodePresence.objects.update_or_create(observed_node=observed_node, defaults={"offline_after": offline_after})
    return watch
