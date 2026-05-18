"""MeshCore-specific node identity helpers (ADR-0001)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.protocol import Protocol

if TYPE_CHECKING:
    from nodes.models import ObservedNode

MC_NODE_ID_STR_PREFIX = "mc:"
MC_PUBKEY_HEX_LEN = 64
MC_PUBKEY_PREFIX_HEX_LEN = 12


def normalize_mc_pubkey(pubkey: Optional[str]) -> Optional[str]:
    """Lowercase 64-char hex pubkey, or None."""
    if not pubkey:
        return None
    cleaned = pubkey.strip().lower().replace("0x", "")
    if len(cleaned) != MC_PUBKEY_HEX_LEN:
        raise ValueError(f"mc_pubkey must be {MC_PUBKEY_HEX_LEN} hex chars, got {len(cleaned)}")
    int(cleaned, 16)  # validate hex
    return cleaned


def normalize_mc_pubkey_prefix(prefix: Optional[str]) -> Optional[str]:
    """Lowercase 12-char hex prefix, or None."""
    if not prefix:
        return None
    cleaned = prefix.strip().lower().replace("0x", "")
    if len(cleaned) != MC_PUBKEY_PREFIX_HEX_LEN:
        raise ValueError(f"mc_pubkey_prefix must be {MC_PUBKEY_PREFIX_HEX_LEN} hex chars, got {len(cleaned)}")
    int(cleaned, 16)
    return cleaned


def pubkey_to_prefix(pubkey: str) -> str:
    """First 12 hex chars of a full pubkey."""
    return normalize_mc_pubkey(pubkey)[:MC_PUBKEY_PREFIX_HEX_LEN]


def mc_node_id_str(*, mc_pubkey: Optional[str] = None, mc_pubkey_prefix: Optional[str] = None) -> str:
    """Display id: mc:{first 12 hex of pubkey or prefix}."""
    if mc_pubkey:
        prefix = pubkey_to_prefix(mc_pubkey)
    elif mc_pubkey_prefix:
        prefix = normalize_mc_pubkey_prefix(mc_pubkey_prefix)
    else:
        raise ValueError("mc_pubkey or mc_pubkey_prefix required for MeshCore node_id_str")
    return f"{MC_NODE_ID_STR_PREFIX}{prefix}"


def prefix_match_queryset(prefix: str):
    """ObservedNode rows that might match a 12-hex prefix sighting."""
    from nodes.models import ObservedNode

    prefix = normalize_mc_pubkey_prefix(prefix)
    return ObservedNode.objects.filter(protocol=Protocol.MESHCORE).filter(
        Q(mc_pubkey_prefix=prefix) | Q(mc_pubkey__startswith=prefix)
    )


@transaction.atomic
def merge_prefix_stub_into_full(full_node: ObservedNode) -> None:
    """Move prefix-stub rows into full_pubkey row per ADR-0001 §8."""
    from nodes.models import ObservedNode

    if not full_node.mc_pubkey:
        return
    prefix = pubkey_to_prefix(full_node.mc_pubkey)
    stubs = ObservedNode.objects.filter(
        protocol=Protocol.MESHCORE,
        mc_pubkey__isnull=True,
        mc_pubkey_prefix=prefix,
    ).exclude(pk=full_node.pk)
    for stub in stubs:
        if stub.last_heard and (not full_node.last_heard or stub.last_heard > full_node.last_heard):
            full_node.last_heard = stub.last_heard
            full_node.save(update_fields=["last_heard"])
        stub.delete()


@transaction.atomic
def resolve_or_create_mc_observed_node(
    *,
    mc_pubkey: Optional[str] = None,
    mc_pubkey_prefix: Optional[str] = None,
    last_heard=None,
    long_name: Optional[str] = None,
    short_name: Optional[str] = None,
) -> ObservedNode:
    """
    Upsert MeshCore ObservedNode per ADR-0001.

    Full pubkey: upsert by mc_pubkey, merge any prefix stubs.
    Prefix only: unique match updates last_heard; zero/multiple matches create or reuse stub.
    """
    from nodes.models import ObservedNode

    if mc_pubkey:
        pubkey = normalize_mc_pubkey(mc_pubkey)
        prefix = pubkey_to_prefix(pubkey)
        defaults = {
            "mc_pubkey_prefix": prefix,
            "node_id_str": mc_node_id_str(mc_pubkey=pubkey),
            "long_name": long_name or f"MC {prefix}",
            "short_name": (short_name or prefix[-4:])[:5],
        }
        if last_heard is not None:
            defaults["last_heard"] = last_heard
        node, created = ObservedNode.objects.get_or_create(
            protocol=Protocol.MESHCORE,
            mc_pubkey=pubkey,
            defaults=defaults,
        )
        if not created:
            update_fields = []
            if last_heard and (not node.last_heard or last_heard > node.last_heard):
                node.last_heard = last_heard
                update_fields.append("last_heard")
            if long_name and node.long_name.startswith("MC "):
                node.long_name = long_name
                update_fields.append("long_name")
            if short_name:
                node.short_name = short_name[:5]
                update_fields.append("short_name")
            if node.mc_pubkey_prefix != prefix:
                node.mc_pubkey_prefix = prefix
                update_fields.append("mc_pubkey_prefix")
            if update_fields:
                node.save(update_fields=update_fields)
        merge_prefix_stub_into_full(node)
        return node

    if mc_pubkey_prefix:
        prefix = normalize_mc_pubkey_prefix(mc_pubkey_prefix)
        matches = list(prefix_match_queryset(prefix))
        if len(matches) == 1:
            node = matches[0]
            if last_heard and (not node.last_heard or last_heard > node.last_heard):
                node.last_heard = last_heard
                node.save(update_fields=["last_heard"])
            return node

        node = ObservedNode.objects.filter(
            protocol=Protocol.MESHCORE,
            mc_pubkey__isnull=True,
            mc_pubkey_prefix=prefix,
        ).first()
        if not node:
            node = ObservedNode.objects.create(
                protocol=Protocol.MESHCORE,
                mc_pubkey_prefix=prefix,
                node_id_str=mc_node_id_str(mc_pubkey_prefix=prefix),
                long_name=long_name or f"MC {prefix}",
                short_name=(short_name or prefix[-4:])[:5],
                last_heard=last_heard,
            )
        elif last_heard and (not node.last_heard or last_heard > node.last_heard):
            node.last_heard = last_heard
            node.save(update_fields=["last_heard"])
        return node

    raise ValueError("mc_pubkey or mc_pubkey_prefix required")
