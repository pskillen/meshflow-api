"""Permission checks for node-related API actions."""

from common.protocol import Protocol
from nodes.models import ManagedNode


def user_can_edit_m2m_opt_out(user, observed_node) -> bool:
    """Staff, the claimant, or the owner of a matching managed node may set opt-out."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if observed_node.claimed_by_id and observed_node.claimed_by_id == user.id:
        return True
    managed = ManagedNode.objects.filter(deleted_at__isnull=True, owner_id=user.id)
    if observed_node.protocol == Protocol.MESHTASTIC and observed_node.meshtastic_node_id:
        if managed.filter(meshtastic_node_id=observed_node.meshtastic_node_id).exists():
            return True
    if observed_node.protocol == Protocol.MESHCORE and observed_node.mc_pubkey:
        if managed.filter(mc_pubkey=observed_node.mc_pubkey).exists():
            return True
    return False


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
