"""ORM side of firmware generation inference. The rules live in ``common.meshtastic_firmware`` (pure).

A verdict is never cleared: ``None`` (no evidence) leaves the stored value alone, so a later keyless NODEINFO or a
malformed key cannot erase what a good key proved.
"""

from __future__ import annotations

from django.utils import timezone

from common.meshtastic_firmware import Evidence, Verdict, classify
from common.protocol import Protocol
from nodes.models import ObservedNode

FIRMWARE_FIELDS = ["inferred_firmware", "inferred_firmware_basis", "inferred_firmware_at"]


def _number_is_another_nodes_key_id(node_num: int | None, *, exclude_pk=None) -> bool:
    if node_num is None:
        return False
    qs = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_key_node_id=node_num)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def build_evidence(node: ObservedNode) -> Evidence:
    key_id = node.meshtastic_key_node_id
    predicted = False
    if key_id is None:
        predicted = _number_is_another_nodes_key_id(node.meshtastic_node_id, exclude_pk=node.pk)
    return Evidence(
        node_num=node.meshtastic_node_id,
        key_node_id=key_id,
        number_is_another_nodes_key_id=predicted,
    )


def apply_verdict(node: ObservedNode, verdict: Verdict | None, *, now=None) -> bool:
    """Set the firmware fields on ``node`` (no save). Returns whether anything changed."""
    if verdict is None:
        return False
    if node.inferred_firmware == verdict.generation and node.inferred_firmware_basis == verdict.basis:
        return False
    node.inferred_firmware = verdict.generation
    node.inferred_firmware_basis = verdict.basis
    node.inferred_firmware_at = now or timezone.now()
    return True


def refresh_inferred_firmware(node: ObservedNode, *, now=None) -> bool:
    """Re-evaluate a Meshtastic node's firmware from what it holds (no save). Returns whether it changed."""
    if node.protocol != Protocol.MESHTASTIC:
        return False
    return apply_verdict(node, classify(build_evidence(node)), now=now)


def predicted_firmware_fields(node_id: int, *, now=None) -> dict:
    """The firmware fields for a brand-new keyless row numbered ``node_id``, or ``{}``."""
    evidence = Evidence(node_num=node_id, number_is_another_nodes_key_id=_number_is_another_nodes_key_id(node_id))
    verdict = classify(evidence)
    if verdict is None:
        return {}
    return {
        "inferred_firmware": verdict.generation,
        "inferred_firmware_basis": verdict.basis,
        "inferred_firmware_at": now or timezone.now(),
    }


def refresh_row_numbered_by_key(node: ObservedNode, *, now=None) -> None:
    """After a key write: re-evaluate keyless Meshtastic rows whose number is this node's key-derived id."""
    key_id = node.meshtastic_key_node_id
    if key_id is None or key_id == node.meshtastic_node_id:
        return
    rows = ObservedNode.objects.filter(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=key_id, meshtastic_key_node_id__isnull=True
    ).exclude(pk=node.pk)
    for row in rows:
        if refresh_inferred_firmware(row, now=now):
            row.save(update_fields=FIRMWARE_FIELDS)
