from rest_framework import permissions


class NoPermission(permissions.BasePermission):
    """
    Permission to allow no access.
    """

    def has_permission(self, request, view):
        return False

    def has_object_permission(self, request, view, obj):
        return False
