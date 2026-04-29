"""Shared helpers for mesh_monitoring tests."""

from mesh_monitoring.models import NodeMonitoringConfig, NodePresence, NodeWatch


def create_watch_with_offline_threshold(*, user, observed_node, offline_after=60, enabled=True):
    """Create a NodeWatch and set the node-level silence threshold on NodeMonitoringConfig."""
    watch = NodeWatch.objects.create(user=user, observed_node=observed_node, enabled=enabled)
    NodePresence.objects.get_or_create(observed_node=observed_node, defaults={"is_offline": False})
    NodeMonitoringConfig.objects.update_or_create(
        observed_node=observed_node,
        defaults={"last_heard_offline_after_seconds": offline_after},
    )
    return watch
