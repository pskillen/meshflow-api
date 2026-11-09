"""ORM side of firmware generation inference. The rules live in ``common.meshtastic_firmware`` (pure).

A verdict is never cleared: ``None`` (no evidence) leaves the stored value alone, so a later keyless NODEINFO or a
malformed key cannot erase what a good key proved.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from common.meshtastic_firmware import Evidence, Verdict, classify
from common.protocol import Protocol
from nodes.models import ManagedNode, ObservedNode

FIRMWARE_FIELDS = ["inferred_firmware", "inferred_firmware_basis", "inferred_firmware_at"]


def _number_is_another_nodes_key_id(node_num: int | None, *, exclude_pk=None) -> bool:
    if node_num is None:
        return False
    qs = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_key_node_id=node_num)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _reporting_feeders():
    return ManagedNode.objects.filter(
        protocol=Protocol.MESHTASTIC, deleted_at__isnull=True, reported_firmware_version__isnull=False
    ).exclude(reported_firmware_version="")


def _feeder_number(feeder: ManagedNode) -> int | None:
    """The number the feeder's radio has now. ``meshtastic_node_id`` goes stale after an upgrade."""
    if feeder.reported_meshtastic_node_id is not None:
        return feeder.reported_meshtastic_node_id
    return feeder.meshtastic_node_id


def feeder_firmware_map() -> dict[int, str]:
    """Node number -> firmware version for every live feeder that has reported one (newest report wins)."""
    firmware: dict[int, str] = {}
    for feeder in _reporting_feeders().order_by("firmware_reported_at", "pk"):
        number = _feeder_number(feeder)
        if number is not None:
            firmware[number] = feeder.reported_firmware_version
    return firmware


def feeder_firmware_for(node_num: int | None) -> str | None:
    """The firmware version the feeder numbered ``node_num`` reported, or None if it is not a reporting feeder."""
    if node_num is None:
        return None
    feeder = (
        _reporting_feeders()
        .filter(
            Q(reported_meshtastic_node_id=node_num)
            | Q(reported_meshtastic_node_id__isnull=True, meshtastic_node_id=node_num)
        )
        .order_by("-firmware_reported_at", "-pk")
        .first()
    )
    return feeder.reported_firmware_version if feeder else None


def build_evidence(node: ObservedNode) -> Evidence:
    key_id = node.meshtastic_key_node_id
    predicted = False
    if key_id is None:
        predicted = _number_is_another_nodes_key_id(node.meshtastic_node_id, exclude_pk=node.pk)
    return Evidence(
        node_num=node.meshtastic_node_id,
        key_node_id=key_id,
        number_is_another_nodes_key_id=predicted,
        feeder_firmware=feeder_firmware_for(node.meshtastic_node_id),
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


def refresh_feeder_row(managed_node: ManagedNode, *, now=None) -> bool:
    """Re-evaluate the feeder's own ObservedNode after it reported firmware. Returns whether the row changed.

    The row is found by the number the feeder reports, falling back to the stored one only when none was reported.
    No row yet is fine: the next report (within 10 minutes) picks it up.
    """
    from nodes.services.observed_nodes import get_meshtastic_observed_node  # it imports this module

    number = _feeder_number(managed_node)
    if number is None:
        return False
    observed = get_meshtastic_observed_node(number)
    if observed is None:
        return False
    if refresh_inferred_firmware(observed, now=now):
        observed.save(update_fields=FIRMWARE_FIELDS)
        return True
    return False


def predicted_firmware_fields(node_id: int, *, now=None) -> dict:
    """The firmware fields for a brand-new keyless row numbered ``node_id``, or ``{}``."""
    evidence = Evidence(
        node_num=node_id,
        number_is_another_nodes_key_id=_number_is_another_nodes_key_id(node_id),
        feeder_firmware=feeder_firmware_for(node_id),
    )
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
