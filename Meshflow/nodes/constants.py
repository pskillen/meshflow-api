"""Shared node-related constants for API and future mesh monitoring."""

from nodes.models import RoleSource

# Infrastructure roles: ROUTER, ROUTER_CLIENT, REPEATER, ROUTER_LATE (optionally CLIENT_BASE elsewhere)
INFRASTRUCTURE_ROLES = [
    RoleSource.ROUTER,
    RoleSource.ROUTER_CLIENT,
    RoleSource.REPEATER,
    RoleSource.ROUTER_LATE,
]
