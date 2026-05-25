"""DRF permission classes for guest / user / feeder / admin access levels."""

from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from common.access import get_access_level, user_is_feeder_or_admin


class AllowGuestReadOnly(permissions.BasePermission):
    """Allow unauthenticated GET/HEAD/OPTIONS; require authentication for writes."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


class IsAuthenticatedUser(permissions.BasePermission):
    """Require a logged-in user (any non-guest level)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsFeederOrAdmin(permissions.BasePermission):
    """Require feeder role or Django staff."""

    message = "Feeder or admin access required."

    def has_permission(self, request, view):
        return user_is_feeder_or_admin(request.user)


class IsSystemAdmin(permissions.BasePermission):
    """Require Django staff."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class AccessLevelMixin:
    """Attach resolved access level to the request for serializers."""

    def initial(self, request, *args, **kwargs):
        request.access_level = get_access_level(request)
        return super().initial(request, *args, **kwargs)
