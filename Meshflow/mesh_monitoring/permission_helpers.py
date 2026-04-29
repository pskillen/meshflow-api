"""Permission checks for mesh monitoring API actions.

See docs/features/mesh-monitoring/permissions.md for the full matrix (watch vs monitoring config).
"""


def user_can_edit_node_monitoring_config(user, observed_node):
    """Django staff or the claim owner may PATCH NodeMonitoringConfig (silence + battery settings)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if observed_node.claimed_by_id and observed_node.claimed_by_id == user.id:
        return True
    return False


def user_can_edit_monitoring_offline_after(user, observed_node):
    """Deprecated alias for :func:`user_can_edit_node_monitoring_config`."""
    return user_can_edit_node_monitoring_config(user, observed_node)
