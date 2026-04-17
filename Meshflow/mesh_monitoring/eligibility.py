"""Who may create a NodeWatch (REST + model validation).

See docs/features/mesh-monitoring/permissions.md for the full permission matrix.
"""

from nodes.constants import INFRASTRUCTURE_ROLES


def user_can_watch(user, observed_node) -> bool:
    if observed_node.claimed_by_id == user.id:
        return True
    if observed_node.role in INFRASTRUCTURE_ROLES:
        return True
    return False
