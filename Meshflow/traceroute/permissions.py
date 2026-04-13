"""Permissions for traceroute triggering."""

from rest_framework import permissions

from .permission_helpers import get_nodes_permitted_for_trigger_queryset


class CanTriggerTraceroute(permissions.BasePermission):
    """
    Allow POST if user has at least one allow_auto_traceroute node they own or can edit.
    Recent ingestion is enforced in the view (400), not here, so offline sources get a clear error.
    """

    message = "You do not have permission to trigger traceroutes."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return get_nodes_permitted_for_trigger_queryset(request.user).exists()
