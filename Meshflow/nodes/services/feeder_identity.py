"""Re-key a feeder whose Meshtastic node number changed (ID-4).

In Meshtastic 2.8 a node's number is ``crc32(public key)``, so a feeder's number changes on a firmware upgrade or
a re-key. The v4 feeder URLs keep ingesting because the API key alone identifies the feeder; this module keeps
``ManagedNode.meshtastic_node_id`` in step with the radio, but only when the change is provable.

``apply_reported_identity`` is called from ``common.feeder_metrics.record_feeder_usage`` (v4 only) whenever the
reported number is (re)written. Rules, first match wins, each flagged row leaves the node untouched:

1. no public key reported -> ``key_not_reported``
2. ``crc32(key)`` is not the reported number -> ``crc_mismatch``
3. a stored key differs from the reported one -> ``key_mismatch`` (a blank stored key passes: trust on first use)
4. another node holds the key (keys are not unique: clones exist) -> ``shared_key``
5. another active feeder already has the reported number -> ``number_collision``
6. ``MESHTASTIC_FEEDER_AUTO_REKEY`` is off -> ``auto_rekey_disabled``
7. otherwise apply, atomically, with an ``auto_updated`` event and ``feeder_identity_changed``.

See docs/features/packet-ingestion/adr/0005-feeder-scoped-auth.md and meshtastic.md ("Feeder number change").
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from prometheus_client import Counter

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import key_node_id, normalise_pubkey
from common.protocol import Protocol
from nodes.managed_node_bootstrap import ensure_observed_node_for_managed_node
from nodes.models import ManagedNode, ManagedNodeIdentityEvent, ObservedNode
from nodes.services.feeder_identity_notify import notify_owner
from nodes.signals import feeder_identity_changed

logger = logging.getLogger(__name__)

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

FEEDER_IDENTITY_CHANGES = Counter(
    "meshflow_feeder_identity_changes_total",
    "Feeder identity events written, by protocol and outcome",
    ["protocol", "outcome"],
)


def _count(outcome: str) -> None:
    try:
        FEEDER_IDENTITY_CHANGES.labels(protocol="meshtastic", outcome=outcome).inc()
    except Exception:
        pass


def _open_flagged(node):
    return ManagedNodeIdentityEvent.objects.filter(managed_node=node, outcome=Outcome.FLAGGED, resolved_at__isnull=True)


def _key_held_by_another_node(node, key_hex: str, old_num: int, new_num: int) -> bool:
    if (
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_public_key_hex=key_hex)
        .exclude(meshtastic_node_id__in=(old_num, new_num))
        .exists()
    ):
        return True
    return (
        ManagedNode.objects.filter(protocol=Protocol.MESHTASTIC, deleted_at__isnull=True, meshtastic_public_key=key_hex)
        .exclude(pk=node.pk)
        .exists()
    )


def _number_held_by_another_feeder(node, num: int) -> bool:
    return (
        ManagedNode.objects.filter(protocol=Protocol.MESHTASTIC, deleted_at__isnull=True, meshtastic_node_id=num)
        .exclude(pk=node.pk)
        .exists()
    )


def _flag(node, *, old_num, new_num, key_hex, reason, now):
    """Write a flagged event unless an open one already says the same; return the event or None."""
    open_rows = list(_open_flagged(node))
    for row in open_rows:
        if row.new_meshtastic_node_id == new_num and row.reported_public_key == key_hex and row.reason == reason:
            return None
    stale = [row.pk for row in open_rows]
    if stale:
        ManagedNodeIdentityEvent.objects.filter(pk__in=stale).update(resolved_at=now)
    event = ManagedNodeIdentityEvent.objects.create(
        managed_node=node,
        old_meshtastic_node_id=old_num,
        new_meshtastic_node_id=new_num,
        reported_public_key=key_hex,
        outcome=Outcome.FLAGGED,
        reason=reason,
    )
    _count(Outcome.FLAGGED)
    logger.warning(
        "Feeder %s (%s) reported node number %s (stored %s): not re-keyed (%s)",
        node.internal_id,
        node.name,
        meshtastic_id_to_hex(new_num),
        meshtastic_id_to_hex(old_num),
        reason,
    )
    notify_owner(event)
    return event


def _lock(node) -> ManagedNode:
    """Re-read the feeder row under a row lock (a seam for the concurrency test)."""
    return ManagedNode.objects.select_for_update().get(pk=node.pk)


def _apply(node, *, old_num, new_num, key_hex, now):
    try:
        with transaction.atomic():
            locked = _lock(node)
            if locked.meshtastic_node_id != old_num:
                # A concurrent request already applied (or changed) the number.
                return None
            locked.meshtastic_node_id = new_num
            locked.meshtastic_public_key = key_hex
            locked.meshtastic_key_node_id = new_num
            locked.save(update_fields=["meshtastic_node_id", "meshtastic_public_key", "meshtastic_key_node_id"])
            _open_flagged(node).update(resolved_at=now)
            event = ManagedNodeIdentityEvent.objects.create(
                managed_node=node,
                old_meshtastic_node_id=old_num,
                new_meshtastic_node_id=new_num,
                reported_public_key=key_hex,
                outcome=Outcome.AUTO_UPDATED,
            )
    except IntegrityError:
        return _flag(node, old_num=old_num, new_num=new_num, key_hex=key_hex, reason=Reason.NUMBER_COLLISION, now=now)

    node.meshtastic_node_id = new_num
    node.meshtastic_public_key = key_hex
    node.meshtastic_key_node_id = new_num
    _count(Outcome.AUTO_UPDATED)
    logger.info(
        "Feeder %s (%s) re-keyed: %s -> %s",
        node.internal_id,
        node.name,
        meshtastic_id_to_hex(old_num),
        meshtastic_id_to_hex(new_num),
    )
    ensure_observed_node_for_managed_node(node)
    feeder_identity_changed.send(
        sender=ManagedNode, managed_node=node, event=event, old_node_id=old_num, new_node_id=new_num
    )
    return event


def _apply_unchanged_number(node, key_hex: Optional[str], now) -> Optional[ManagedNodeIdentityEvent]:
    _open_flagged(node).update(resolved_at=now)
    if key_hex is None:
        return None
    stored = normalise_pubkey(node.meshtastic_public_key)
    if stored == key_hex:
        return None
    fields = {"meshtastic_public_key": key_hex, "meshtastic_key_node_id": key_node_id(key_hex)}
    ManagedNode.objects.filter(pk=node.pk).update(**fields)
    for name, value in fields.items():
        setattr(node, name, value)
    if stored is None:
        # Trust on first use (ADR-0005): filling a blank key is not an event.
        return None
    event = ManagedNodeIdentityEvent.objects.create(
        managed_node=node,
        old_meshtastic_node_id=node.meshtastic_node_id,
        new_meshtastic_node_id=node.meshtastic_node_id,
        reported_public_key=key_hex,
        outcome=Outcome.KEY_CHANGED,
    )
    _count(Outcome.KEY_CHANGED)
    logger.info(
        "Feeder %s (%s) reported a new public key for %s",
        node.internal_id,
        node.name,
        meshtastic_id_to_hex(node.meshtastic_node_id),
    )
    return event


def apply_reported_identity(
    node: ManagedNode, *, reported_node_num: int, reported_pubkey: Optional[str], now=None
) -> Optional[ManagedNodeIdentityEvent]:
    """Decide what a feeder's reported number and public key mean for ``node``; return the event written, if any."""
    if node.protocol != Protocol.MESHTASTIC or reported_node_num is None:
        return None
    now = now or timezone.now()
    key_hex = normalise_pubkey(reported_pubkey)
    old_num = node.meshtastic_node_id

    if reported_node_num == old_num:
        return _apply_unchanged_number(node, key_hex, now)

    def flag(reason):
        return _flag(node, old_num=old_num, new_num=reported_node_num, key_hex=key_hex, reason=reason, now=now)

    if key_hex is None:
        return flag(Reason.KEY_NOT_REPORTED)
    if key_node_id(key_hex) != reported_node_num:
        return flag(Reason.CRC_MISMATCH)
    stored = normalise_pubkey(node.meshtastic_public_key)
    if stored is not None and stored != key_hex:
        return flag(Reason.KEY_MISMATCH)
    if _key_held_by_another_node(node, key_hex, old_num, reported_node_num):
        return flag(Reason.SHARED_KEY)
    if _number_held_by_another_feeder(node, reported_node_num):
        return flag(Reason.NUMBER_COLLISION)
    if not getattr(settings, "MESHTASTIC_FEEDER_AUTO_REKEY", False):
        return flag(Reason.AUTO_REKEY_DISABLED)
    return _apply(node, old_num=old_num, new_num=reported_node_num, key_hex=key_hex, now=now)
