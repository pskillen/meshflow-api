"""Permission checks for node-related API actions."""


def user_can_edit_observed_node_environment_settings(user, observed_node):
    """
    Staff or the user who has claimed the observed node (claimed_by) may edit
    environment exposure / weather_use.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if observed_node.claimed_by_id and observed_node.claimed_by_id == user.id:
        return True
    return False


def user_can_edit_observed_node_rf_profile(user, observed_node) -> bool:
    """Staff or the user who has claimed the observed node may edit the RF profile."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return bool(observed_node.claimed_by_id and observed_node.claimed_by_id == user.id)
