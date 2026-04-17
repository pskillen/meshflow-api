"""Permission checks for mesh monitoring API actions.

See docs/features/mesh-monitoring/permissions.md for the full matrix (watch vs offline_after).
"""


def user_can_edit_monitoring_offline_after(user, observed_node):
    """Django staff or the claim owner may PATCH NodePresence.offline_after (silence threshold)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if observed_node.claimed_by_id and observed_node.claimed_by_id == user.id:
        return True
    return False
