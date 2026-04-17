"""Permission checks for mesh monitoring API actions."""


def user_can_edit_monitoring_offline_after(user, observed_node):
    """Staff or the user who claimed the observed node may edit silence threshold."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if observed_node.claimed_by_id and observed_node.claimed_by_id == user.id:
        return True
    return False
