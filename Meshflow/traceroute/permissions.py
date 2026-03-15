"""Permissions for traceroute triggering."""

from rest_framework import permissions

from .permission_helpers import get_triggerable_nodes_queryset


class CanTriggerTraceroute(permissions.BasePermission):
    """
    Allow triggering traceroutes if user has at least one triggerable node
    (staff, constellation admin/editor, or ManagedNode owner).
    """

    message = "You do not have permission to trigger traceroutes."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return get_triggerable_nodes_queryset(request.user).exists()
