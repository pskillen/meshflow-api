"""Resolve MeshCore feeder ManagedNode from API key + URL pubkey prefix."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from common.meshcore_node_helpers import (
    normalize_mc_pubkey,
    normalize_mc_pubkey_prefix,
    pubkey_to_prefix,
)
from common.protocol import Protocol
from nodes.models import ManagedNode, NodeAuth

if TYPE_CHECKING:
    from nodes.models import NodeAPIKey


@dataclass(frozen=True)
class MeshCoreFeederResolutionError(Exception):
    """Feeder could not be resolved for this request."""

    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def resolve_meshcore_feeder(
    *,
    api_key: NodeAPIKey,
    feeder_pubkey_prefix: str,
    feeder_pubkey_full: Optional[str] = None,
) -> ManagedNode:
    """
    Pick the MeshCore ManagedNode for a feeder-scoped request.

    Raises MeshCoreFeederResolutionError with a stable ``code`` for 403 responses.
    """
    try:
        prefix = normalize_mc_pubkey_prefix(feeder_pubkey_prefix)
    except ValueError as exc:
        raise MeshCoreFeederResolutionError(
            code="invalid_feeder_pubkey_prefix",
            detail=str(exc),
        ) from exc

    auths = list(
        NodeAuth.objects.filter(
            api_key=api_key,
            node__protocol=Protocol.MESHCORE,
            node__deleted_at__isnull=True,
        ).select_related("node", "node__constellation")
    )
    if not auths:
        raise MeshCoreFeederResolutionError(
            code="feeder_not_linked",
            detail="API key is not linked to a MeshCore feeder.",
        )

    if len(auths) > 1:
        missing_pubkey = [a for a in auths if not a.node.mc_pubkey]
        if missing_pubkey:
            raise MeshCoreFeederResolutionError(
                code="feeder_pubkey_not_configured",
                detail=(
                    "Multiple MeshCore feeders share this API key; each ManagedNode "
                    "must have mc_pubkey set in admin."
                ),
            )

    matches: list[ManagedNode] = []
    for node_auth in auths:
        node = node_auth.node
        if not node.mc_pubkey:
            continue
        try:
            if pubkey_to_prefix(node.mc_pubkey) == prefix:
                matches.append(node)
        except ValueError:
            continue

    if len(matches) == 0:
        raise MeshCoreFeederResolutionError(
            code="feeder_not_linked",
            detail="No MeshCore feeder linked to this API key matches the URL pubkey prefix.",
        )
    if len(matches) > 1:
        raise MeshCoreFeederResolutionError(
            code="feeder_identity_ambiguous",
            detail="Multiple MeshCore feeders match this API key and pubkey prefix.",
        )

    node = matches[0]
    if feeder_pubkey_full:
        try:
            full = normalize_mc_pubkey(feeder_pubkey_full)
        except ValueError as exc:
            raise MeshCoreFeederResolutionError(
                code="invalid_feeder_pubkey",
                detail=str(exc),
            ) from exc
        if node.mc_pubkey and full != node.mc_pubkey:
            raise MeshCoreFeederResolutionError(
                code="feeder_pubkey_mismatch",
                detail="X-MeshCore-Feeder-Pubkey does not match the configured feeder.",
            )

    return node
