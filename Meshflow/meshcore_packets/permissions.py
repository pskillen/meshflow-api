"""Permissions for MeshCore feeder ingest (feeder pubkey prefix in URL)."""

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from common.meshcore_feeder_auth import MeshCoreFeederResolutionError, resolve_meshcore_feeder


class MeshCoreFeederPermission(permissions.BasePermission):
    """Resolve ManagedNode from API key + ``feeder_pubkey_prefix`` URL kwarg."""

    def has_permission(self, request, view):
        if not request.auth:
            return False

        prefix = view.kwargs.get("feeder_pubkey_prefix")
        if not prefix:
            return False

        header_full = request.META.get("HTTP_X_MESHCORE_FEEDER_PUBKEY")
        try:
            node = resolve_meshcore_feeder(
                api_key=request.auth,
                feeder_pubkey_prefix=prefix,
                feeder_pubkey_full=header_full,
            )
        except MeshCoreFeederResolutionError as exc:
            raise PermissionDenied(detail={"detail": exc.detail, "code": exc.code}) from exc

        request.auth.node = node
        return True
