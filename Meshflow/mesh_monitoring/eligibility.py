"""Who may create a NodeWatch (same rules as future REST API)."""

from nodes.constants import INFRASTRUCTURE_ROLES


def user_can_watch(user, observed_node) -> bool:
    if observed_node.claimed_by_id == user.id:
        return True
    if observed_node.role in INFRASTRUCTURE_ROLES:
        return True
    return False
