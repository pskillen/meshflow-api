"""Global access levels for Meshflow API authorization."""

from enum import StrEnum

from django.contrib.auth.models import Group

FEEDER_GROUP_NAME = "feeder"


class AccessLevel(StrEnum):
    GUEST = "guest"
    USER = "user"
    FEEDER = "feeder"
    ADMIN = "admin"


def user_is_feeder(user) -> bool:
    """True when the user is in the feeder group (trusted operator)."""
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=FEEDER_GROUP_NAME).exists()


def user_is_feeder_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user_is_feeder(user)


def user_can_manage_api_keys(user) -> bool:
    return user_is_feeder_or_admin(user)


def get_access_level(request) -> AccessLevel:
    """Resolve the effective access level for an HTTP request."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return AccessLevel.GUEST
    if user.is_staff:
        return AccessLevel.ADMIN
    if user_is_feeder(user):
        return AccessLevel.FEEDER
    return AccessLevel.USER


def ensure_feeder_group():
    """Create the feeder Django group if missing."""
    Group.objects.get_or_create(name=FEEDER_GROUP_NAME)


def grant_feeder_role(user):
    """Add user to the feeder group."""
    ensure_feeder_group()
    group = Group.objects.get(name=FEEDER_GROUP_NAME)
    user.groups.add(group)
