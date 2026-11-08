"""Feeder-scoped authentication for the v4 feeder URLs (ADR-0005).

A v4 request is authorised on the API key alone: the key must be linked to exactly one active
``ManagedNode``. The feeder's node number is never part of the decision, so a Meshtastic 2.8
feeder whose number changes keeps ingesting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from common.feeder_metrics import API_V4, record_feeder_auth_rejection
from common.protocol import Protocol
from nodes.models import NodeAuth

if TYPE_CHECKING:
    from nodes.models import ManagedNode, NodeAPIKey

FEEDER_NOT_LINKED = "feeder_not_linked"
SHARED_API_KEY = "shared_api_key"
FEEDER_PROTOCOL_MISMATCH = "feeder_protocol_mismatch"

_PROTOCOL_LABELS = {
    Protocol.MESHTASTIC: "Meshtastic",
    Protocol.MESHCORE: "MeshCore",
}


@dataclass(frozen=True)
class FeederResolutionError(Exception):
    """The API key does not identify exactly one feeder of the right protocol."""

    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def resolve_single_feeder(api_key: NodeAPIKey, *, protocol: Optional[int] = None) -> ManagedNode:
    """Return the one active ManagedNode linked to ``api_key``.

    Raises FeederResolutionError with code ``feeder_not_linked`` (no active feeder),
    ``shared_api_key`` (more than one, whatever their protocols) or ``feeder_protocol_mismatch``
    (the single feeder is not of ``protocol``).
    """
    auths = list(
        NodeAuth.objects.select_related("node", "node__constellation").filter(
            api_key=api_key,
            node__deleted_at__isnull=True,
        )[:2]
    )
    if not auths:
        raise FeederResolutionError(
            code=FEEDER_NOT_LINKED,
            detail="This API key is not linked to an active feeder.",
        )
    if len(auths) > 1:
        raise FeederResolutionError(
            code=SHARED_API_KEY,
            detail=(
                "This API key is linked to more than one feeder. The v4 feeder URLs need one API key "
                "per feeder: create a key for each feeder on the API keys page and configure each bot "
                "with its own key. The legacy feeder URLs still accept shared keys."
            ),
        )

    node = auths[0].node
    if protocol is not None and node.protocol != protocol:
        raise FeederResolutionError(
            code=FEEDER_PROTOCOL_MISMATCH,
            detail=(
                f"This API key belongs to a {_PROTOCOL_LABELS.get(node.protocol, 'different')} feeder; "
                f"this endpoint is for {_PROTOCOL_LABELS.get(protocol, 'other')} feeders."
            ),
        )
    return node


class FeederScopedPermission(permissions.BasePermission):
    """Resolve the feeder from the API key alone (v4 feeder URLs).

    Reads ``view.feeder_protocol`` (a ``Protocol`` value, or None for protocol-neutral endpoints),
    attaches the feeder to ``request.auth.node`` and raises 403 ``{"detail", "code"}`` on failure.
    """

    def has_permission(self, request, view):
        if not request.auth:
            return False

        try:
            node = resolve_single_feeder(request.auth, protocol=getattr(view, "feeder_protocol", None))
        except FeederResolutionError as exc:
            record_feeder_auth_rejection(api=API_V4, code=exc.code)
            raise PermissionDenied(detail={"detail": exc.detail, "code": exc.code}) from exc

        request.auth.node = node
        return True
