"""Resolve Meshtastic feeder ManagedNode from API key + node id."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from common.mesh_node_helpers import (
    meshtastic_hex_to_int,
    normalize_meshtastic_lookup_hex,
)
from common.protocol import Protocol
from nodes.models import NodeAuth

if TYPE_CHECKING:
    from nodes.models import ManagedNode, NodeAPIKey


@dataclass(frozen=True)
class MeshtasticFeederResolutionError(Exception):
    """Feeder could not be resolved for this request."""

    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def resolve_meshtastic_feeder(
    *,
    api_key: NodeAPIKey,
    feeder_node_id: Optional[int] = None,
    feeder_node_id_str: Optional[str] = None,
) -> ManagedNode:
    """
    Pick the Meshtastic ManagedNode for a feeder-scoped request.

    Raises MeshtasticFeederResolutionError with a stable ``code`` when resolution fails.
    """
    node_id = _resolve_meshtastic_node_id(
        feeder_node_id=feeder_node_id,
        feeder_node_id_str=feeder_node_id_str,
    )

    try:
        node_auth = NodeAuth.objects.select_related("node", "node__constellation").get(
            api_key=api_key,
            node__protocol=Protocol.MESHTASTIC,
            node__meshtastic_node_id=node_id,
            node__deleted_at__isnull=True,
        )
    except NodeAuth.DoesNotExist:
        raise MeshtasticFeederResolutionError(
            code="feeder_not_linked",
            detail="API key is not linked to a Meshtastic feeder with this node id.",
        ) from None

    return node_auth.node


def _resolve_meshtastic_node_id(
    *,
    feeder_node_id: Optional[int] = None,
    feeder_node_id_str: Optional[str] = None,
) -> int:
    if feeder_node_id is not None and feeder_node_id_str:
        raise MeshtasticFeederResolutionError(
            code="invalid_feeder_node_id",
            detail="Pass feeder_node_id or feeder_node_id_str, not both.",
        )

    if feeder_node_id is not None:
        return feeder_node_id

    if feeder_node_id_str:
        token = feeder_node_id_str.strip()
        hex_part = normalize_meshtastic_lookup_hex(token)
        if hex_part:
            return int(hex_part, 16)
        if token.startswith("!") or token == "^all":
            try:
                return meshtastic_hex_to_int(token)
            except ValueError as exc:
                raise MeshtasticFeederResolutionError(
                    code="invalid_feeder_node_id_str",
                    detail=str(exc),
                ) from exc
        raise MeshtasticFeederResolutionError(
            code="invalid_feeder_node_id_str",
            detail="feeder_node_id_str must be !xxxxxxxx or 8 hex digits.",
        )

    raise MeshtasticFeederResolutionError(
        code="missing_feeder_node_id",
        detail="feeder_node_id or feeder_node_id_str is required.",
    )
