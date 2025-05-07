from rest_framework import permissions

from .models import ConstellationUserMembership


class IsConstellationMember(permissions.BasePermission):
    """
    Permission to only allow members of a constellation to access the view.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        constellation_id = view.kwargs.get("constellation_id") or view.kwargs.get("pk")
        if not constellation_id:
            return False
        return ConstellationUserMembership.objects.filter(user=request.user, constellation_id=constellation_id).exists()

    def has_object_permission(self, request, view, obj):
        return ConstellationUserMembership.objects.filter(user=request.user, constellation=obj).exists()


class IsConstellationEditorOrAdmin(permissions.BasePermission):
    """
    Permission to only allow editors or admins of a constellation to access the view.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        constellation_id = view.kwargs.get("constellation_id") or view.kwargs.get("pk")
        if not constellation_id:
            return False
        return ConstellationUserMembership.objects.filter(
            user=request.user, constellation_id=constellation_id, role__in=["admin", "editor"]
        ).exists()

    def has_object_permission(self, request, view, obj):
        return ConstellationUserMembership.objects.filter(
            user=request.user, constellation=obj, role__in=["admin", "editor"]
        ).exists()


class IsConstellationAdmin(permissions.BasePermission):
    """
    Permission to only allow admins of a constellation to access the view.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        constellation_id = view.kwargs.get("constellation_id") or view.kwargs.get("pk")
        if not constellation_id:
            return False
        return ConstellationUserMembership.objects.filter(
            user=request.user, constellation_id=constellation_id, role="admin"
        ).exists()

    def has_object_permission(self, request, view, obj):
        return ConstellationUserMembership.objects.filter(user=request.user, constellation=obj, role="admin").exists()
