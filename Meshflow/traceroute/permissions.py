"""Permissions for traceroute triggering."""

from rest_framework import permissions

from constellations.models import ConstellationUserMembership


class CanTriggerTraceroute(permissions.BasePermission):
    """
    Allow triggering traceroutes if user is staff or has admin/editor role
    in the ManagedNode's constellation.
    """

    message = "You do not have permission to trigger traceroutes."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return ConstellationUserMembership.objects.filter(
            user=request.user,
            role__in=["admin", "editor"],
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation=obj.source_node.constellation,
            role__in=["admin", "editor"],
        ).exists()
