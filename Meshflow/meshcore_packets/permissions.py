"""Permissions for MeshCore feeder ingest (no URL node_id)."""

from rest_framework import permissions

from common.protocol import Protocol
from nodes.models import NodeAuth


class MeshCoreFeederPermission(permissions.BasePermission):
    """Attach the ManagedNode linked to the API key for MeshCore ingest."""

    def has_permission(self, request, view):
        if not request.auth:
            return False
        try:
            node_auth = NodeAuth.objects.select_related("node", "node__constellation").get(api_key=request.auth)
        except NodeAuth.DoesNotExist:
            return False
        if node_auth.node.deleted_at is not None:
            return False
        if node_auth.node.protocol != Protocol.MESHCORE:
            return False
        request.auth.node = node_auth.node
        return True
