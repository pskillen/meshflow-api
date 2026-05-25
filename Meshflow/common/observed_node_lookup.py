"""Resolve ObservedNode detail lookups from URL path segments (UI #280)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from common.mesh_node_helpers import (
    MT_NODE_ID_STR_PREFIX,
    meshtastic_hex_to_int,
    normalize_meshtastic_lookup_hex,
)
from common.meshcore_node_helpers import MC_NODE_ID_STR_PREFIX, normalize_mc_pubkey_prefix, prefix_match_queryset
from common.protocol import Protocol

if TYPE_CHECKING:
    from nodes.models import ObservedNode


@dataclass(frozen=True)
class ObservedNodeLookupResolved:
    node: ObservedNode


@dataclass(frozen=True)
class ObservedNodeLookupAmbiguous:
    choices: tuple[ObservedNode, ...]


@dataclass(frozen=True)
class ObservedNodeLookupNotFound:
    pass


ObservedNodeLookupResult = Union[
    ObservedNodeLookupResolved,
    ObservedNodeLookupAmbiguous,
    ObservedNodeLookupNotFound,
]

_UUID_RE = None  # lazy


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _meshtastic_node_by_id(meshtastic_node_id: int) -> Optional[ObservedNode]:
    from nodes.models import ObservedNode

    return (
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=meshtastic_node_id)
        .order_by("pk")
        .first()
    )


def _meshtastic_from_hex_token(token: str) -> Optional[ObservedNode]:
    hex_part = normalize_meshtastic_lookup_hex(token)
    if not hex_part:
        return None
    try:
        node_id = meshtastic_hex_to_int(f"!{hex_part}")
    except ValueError:
        return None
    return _meshtastic_node_by_id(node_id)


def _meshcore_from_mc_token(suffix: str) -> Optional[ObservedNode]:
    cleaned = suffix.strip().lower().replace("0x", "")
    if not cleaned or not all(c in "0123456789abcdef" for c in cleaned):
        return None
    from nodes.models import ObservedNode

    if len(cleaned) == 12:
        try:
            prefix = normalize_mc_pubkey_prefix(cleaned)
        except ValueError:
            return None
        matches = list(prefix_match_queryset(prefix)[:2])
        if len(matches) == 1:
            return matches[0]
        return None

    qs = ObservedNode.objects.filter(protocol=Protocol.MESHCORE).filter(models_q_mc_hex_substring(cleaned))
    matches = list(qs.order_by("pk")[:2])
    if len(matches) == 1:
        return matches[0]
    return None


def models_q_mc_hex_substring(hexish: str):
    from django.db.models import Q

    return Q(mc_pubkey__icontains=hexish) | Q(mc_pubkey_prefix__icontains=hexish)


def _meshcore_bare_hex(hexish: str) -> Optional[ObservedNode]:
    from nodes.models import ObservedNode

    if len(hexish) == 12:
        try:
            prefix = normalize_mc_pubkey_prefix(hexish)
        except ValueError:
            return None
        matches = list(prefix_match_queryset(prefix)[:2])
        if len(matches) == 1:
            return matches[0]
        return None

    qs = ObservedNode.objects.filter(protocol=Protocol.MESHCORE).filter(models_q_mc_hex_substring(hexish))
    matches = list(qs.order_by("pk")[:2])
    if len(matches) == 1:
        return matches[0]
    return None


def _combine_bare(mt: Optional[ObservedNode], mc: Optional[ObservedNode]) -> ObservedNodeLookupResult:
    if mt is not None and mc is not None and mt.pk != mc.pk:
        return ObservedNodeLookupAmbiguous(choices=(mt, mc))
    if mt is not None:
        return ObservedNodeLookupResolved(node=mt)
    if mc is not None:
        return ObservedNodeLookupResolved(node=mc)
    return ObservedNodeLookupNotFound()


def resolve_observed_node_lookup(lookup: str) -> ObservedNodeLookupResult:
    """
    Resolve a path/query segment to zero, one, or two (ambiguous) ObservedNode rows.

    Supports UUID, ``mt:`` / ``!`` Meshtastic hex, ``mc:`` prefix, legacy decimal
    Meshtastic node id, and bare hex.
    """
    from nodes.models import ObservedNode

    raw = (lookup or "").strip()
    if not raw:
        return ObservedNodeLookupNotFound()

    if _is_uuid(raw):
        try:
            node = ObservedNode.objects.get(internal_id=raw)
            return ObservedNodeLookupResolved(node=node)
        except ObservedNode.DoesNotExist:
            return ObservedNodeLookupNotFound()

    lower = raw.lower()

    if lower.startswith(MC_NODE_ID_STR_PREFIX):
        suffix = raw[len(MC_NODE_ID_STR_PREFIX) :]
        node = _meshcore_from_mc_token(suffix)
        if node is None:
            return ObservedNodeLookupNotFound()
        return ObservedNodeLookupResolved(node=node)

    if raw.startswith("!") or lower.startswith(MT_NODE_ID_STR_PREFIX):
        node = _meshtastic_from_hex_token(raw)
        if node is None:
            return ObservedNodeLookupNotFound()
        return ObservedNodeLookupResolved(node=node)

    if raw.isdigit():
        node = _meshtastic_node_by_id(int(raw))
        if node is not None:
            return ObservedNodeLookupResolved(node=node)

    hexish = lower.replace("0x", "")
    if hexish and all(c in "0123456789abcdef" for c in hexish):
        mt = None
        if len(hexish) == 8:
            mt = _meshtastic_from_hex_token(hexish)
        mc = _meshcore_bare_hex(hexish)
        return _combine_bare(mt, mc)

    return ObservedNodeLookupNotFound()


def build_ambiguous_lookup_response(choices: tuple) -> dict:
    return {
        "detail": "Multiple nodes match this id.",
        "choices": [observed_node_lookup_choice_payload(n) for n in choices],
    }


def ambiguous_lookup_exception(choices: tuple):
    """DRF exception for nested detail routes with an ambiguous path id."""
    from rest_framework.exceptions import APIException

    class ObservedNodeLookupAmbiguousException(APIException):
        status_code = 300
        default_code = "ambiguous_node_lookup"

    exc = ObservedNodeLookupAmbiguousException()
    exc.detail = build_ambiguous_lookup_response(choices)
    return exc


def observed_node_lookup_choice_payload(node: ObservedNode) -> dict:
    from common.mesh_node_helpers import observed_node_id_str

    return {
        "internal_id": str(node.internal_id),
        "protocol": node.protocol,
        "node_id_str": observed_node_id_str(node),
        "short_name": node.short_name or "",
        "long_name": node.long_name or "",
    }
