"""Re-key a feeder whose Meshtastic node number changed (ID-4).

In Meshtastic 2.8 a node's number is ``crc32(public key)``, so a feeder's number changes on a firmware upgrade or
a re-key. The v4 feeder URLs keep ingesting because the API key alone identifies the feeder; this module keeps
``ManagedNode.meshtastic_node_id`` in step with the radio, but only when the change is provable.

``apply_reported_identity`` is called from ``common.feeder_metrics.record_feeder_usage`` (v4 only) whenever the
reported number is (re)written. Rules, first match wins, each flagged row leaves the node untouched:

1. no public key reported -> ``key_not_reported``
2. ``crc32(key)`` is not the reported number -> ``crc_mismatch``
3. the number is outside the valid node range -> ``number_collision``
4. the reported key is not one already trusted for this feeder (stored before this report and settled) ->
   ``key_mismatch``
5. another node holds the key (keys are not unique: clones exist) -> ``shared_key``
6. another active feeder already has the reported number -> ``number_collision``
7. an ``ObservedNode`` at the reported number carries a different key -> ``key_mismatch``, or belongs to someone else
   -> ``number_collision``
8. ``MESHTASTIC_FEEDER_AUTO_REKEY`` is off, or the newest manual re-point moved the feeder away from the reported
   number (a manual reversal holds) -> ``auto_rekey_disabled``
9. otherwise apply, atomically, with an ``auto_updated`` event and ``feeder_identity_changed``. The ``ObservedNode``
   at the new number is claimed for the owner only when the key did not come from a feeder report.

crc32 is forgeable, so a match shows the report is consistent, not who sent it. Hence rows 4 and 7.

See docs/features/packet-ingestion/adr/0005-feeder-scoped-auth.md and meshtastic.md ("Feeder number change").
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from prometheus_client import Counter

from common.mesh_node_helpers import MESHTASTIC_BROADCAST_ID, meshtastic_id_to_hex
from common.meshtastic_identity import key_node_id, normalise_pubkey
from common.protocol import Protocol
from nodes.managed_node_bootstrap import ensure_observed_node_for_managed_node
from nodes.models import ManagedNode, ManagedNodeIdentityEvent, NodeOwnerClaim, ObservedNode
from nodes.services.feeder_identity_notify import queue_owner_notification
from nodes.signals import feeder_identity_changed

logger = logging.getLogger(__name__)

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

# Firmware NodeDB.cpp NUM_RESERVED: numbers below this are never given to a radio.
MIN_MESHTASTIC_NODE_NUM = 4
# A first key recorded from a report must be this old before it can back a number change. Longer than the 10-minute
# report interval, so the very next report can't use it; a real feeder inside the window is re-evaluated and applied
# by a later report.
FIRST_KEY_SETTLE = timedelta(hours=1)

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


def _is_valid_node_num(num: int) -> bool:
    return MIN_MESHTASTIC_NODE_NUM <= num < MESHTASTIC_BROADCAST_ID


def _is_trusted_key(node, key_hex: str, now) -> bool:
    """True when ``key_hex`` is the feeder's stored key and was not first recorded from a report just now.

    A key filled in from a report leaves a ``key_changed`` event; a key with no such event came from the backfill.
    """
    if normalise_pubkey(node.meshtastic_public_key) != key_hex:
        return False
    return not node.identity_events.filter(
        outcome=Outcome.KEY_CHANGED, reported_public_key=key_hex, created_at__gt=now - FIRST_KEY_SETTLE
    ).exists()


def _key_came_from_report(node, key_hex: str) -> bool:
    """True when a feeder report recorded ``key_hex``, so it proves nothing about who holds the radio."""
    return node.identity_events.filter(
        outcome__in=(Outcome.KEY_CHANGED, Outcome.KEY_ACCEPTED), reported_public_key=key_hex
    ).exists()


def _observed_at(num: int) -> Optional[ObservedNode]:
    return ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=num).first()


def _carries_other_key(observed: Optional[ObservedNode], key_hex: str) -> bool:
    return (
        observed is not None
        and bool(observed.meshtastic_public_key_hex)
        and observed.meshtastic_public_key_hex != key_hex
    )


def _belongs_to_someone_else(observed: Optional[ObservedNode], owner_id) -> bool:
    if observed is None:
        return False
    if observed.claimed_by_id is not None and observed.claimed_by_id != owner_id:
        return True
    return NodeOwnerClaim.objects.filter(node=observed, accepted_at__isnull=False).exclude(user_id=owner_id).exists()


def _reversed_by_hand(node, num: int) -> bool:
    """True when the feeder's newest manual re-point moved it away from ``num``."""
    newest = node.identity_events.filter(outcome=Outcome.MANUAL).order_by("-created_at", "-id").first()
    return newest is not None and newest.old_meshtastic_node_id == num


def _flag(node, *, old_num, new_num, key_hex, reason, now):
    """Write a flagged event unless an open one already says the same; return the event or None."""
    with transaction.atomic():
        # Serialises concurrent reports from one feeder, so the dedupe below can't write two open rows.
        ManagedNode.objects.select_for_update().filter(pk=node.pk).first()
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
    queue_owner_notification(event)
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
    _after_commit(node, event, old_num, new_num, claim=not _key_came_from_report(node, key_hex))
    return event


def _apply_unchanged_number(node, key_hex: Optional[str], now) -> Optional[ManagedNodeIdentityEvent]:
    number = node.meshtastic_node_id
    stored = normalise_pubkey(node.meshtastic_public_key)
    if key_hex is not None:
        contradicted = stored != key_hex if stored is not None else _carries_other_key(_observed_at(number), key_hex)
        if contradicted:
            # Evidence only: a report never replaces a key we hold, or it could vouch for a later number change.
            return _flag(node, old_num=number, new_num=number, key_hex=key_hex, reason=Reason.KEY_MISMATCH, now=now)
    _open_flagged(node).update(resolved_at=now)
    if key_hex is None or stored == key_hex:
        return None
    # First key for this feeder (trust on first use, ADR-0005). The event dates it for _is_trusted_key.
    fields = {"meshtastic_public_key": key_hex, "meshtastic_key_node_id": key_node_id(key_hex)}
    with transaction.atomic():
        ManagedNode.objects.filter(pk=node.pk).update(**fields)
        event = ManagedNodeIdentityEvent.objects.create(
            managed_node=node,
            old_meshtastic_node_id=number,
            new_meshtastic_node_id=number,
            reported_public_key=key_hex,
            outcome=Outcome.KEY_CHANGED,
        )
    for name, value in fields.items():
        setattr(node, name, value)
    _count(Outcome.KEY_CHANGED)
    logger.info(
        "Feeder %s (%s) recorded its first public key on %s", node.internal_id, node.name, meshtastic_id_to_hex(number)
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
    if not _is_valid_node_num(reported_node_num):
        return flag(Reason.NUMBER_COLLISION)
    if not _is_trusted_key(node, key_hex, now):
        return flag(Reason.KEY_MISMATCH)
    if _key_held_by_another_node(node, key_hex, old_num, reported_node_num):
        return flag(Reason.SHARED_KEY)
    if _number_held_by_another_feeder(node, reported_node_num):
        return flag(Reason.NUMBER_COLLISION)
    target = _observed_at(reported_node_num)
    if _carries_other_key(target, key_hex):
        return flag(Reason.KEY_MISMATCH)
    if _belongs_to_someone_else(target, node.owner_id):
        return flag(Reason.NUMBER_COLLISION)
    if not getattr(settings, "MESHTASTIC_FEEDER_AUTO_REKEY", False) or _reversed_by_hand(node, reported_node_num):
        return flag(Reason.AUTO_REKEY_DISABLED)
    return _apply(node, old_num=old_num, new_num=reported_node_num, key_hex=key_hex, now=now)


class FeederRepointError(Exception):
    """A manual re-point was refused; ``code`` is one of the ``CODE_*`` values (the API's ``code`` field)."""

    CODE_NOT_MESHTASTIC = "not_meshtastic"
    CODE_NO_REPORTED_NUMBER = "no_reported_number"
    CODE_INVALID_NODE_ID = "invalid_node_id"
    CODE_ALREADY_CURRENT = "already_current"
    CODE_NUMBER_COLLISION = "number_collision"
    CODE_NOT_PROVEN = "repoint_not_proven"
    CODE_TARGET_KEY_MISMATCH = "repoint_target_key_mismatch"
    CODE_TARGET_CLAIMED = "repoint_target_claimed"
    CODE_STAFF_ONLY = "staff_only"
    CODE_NO_KEY_TO_ACCEPT = "no_key_to_accept"

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# HTTP status for each refusal; any code not listed is a 400.
REPOINT_HTTP_STATUS = {
    FeederRepointError.CODE_NUMBER_COLLISION: 409,
    FeederRepointError.CODE_NOT_PROVEN: 403,
    FeederRepointError.CODE_TARGET_KEY_MISMATCH: 409,
    FeederRepointError.CODE_TARGET_CLAIMED: 409,
    FeederRepointError.CODE_STAFF_ONLY: 403,
}


def _valid_node_number(num) -> bool:
    return isinstance(num, int) and not isinstance(num, bool) and 4 <= num < MESHTASTIC_BROADCAST_ID


def _owner_may_repoint(locked, new_number, now) -> bool:
    """True when ``new_number`` is the feeder's last reported number and crc32 of its trusted stored key gives it."""
    key_hex = normalise_pubkey(locked.meshtastic_public_key)
    return (
        new_number == locked.reported_meshtastic_node_id
        and key_hex is not None
        and key_node_id(key_hex) == new_number
        and _is_trusted_key(locked, key_hex, now)
    )


def _check_owner_target(locked, new_number) -> None:
    """Refuse an owner's re-point onto a node the automatic re-key would flag: another key, or someone else's."""
    target = _observed_at(new_number)
    if _carries_other_key(target, normalise_pubkey(locked.meshtastic_public_key)):
        raise FeederRepointError(
            FeederRepointError.CODE_TARGET_KEY_MISMATCH, "The node at that number has a different public key."
        )
    if _belongs_to_someone_else(target, locked.owner_id):
        raise FeederRepointError(
            FeederRepointError.CODE_TARGET_CLAIMED, "The node at that number belongs to someone else."
        )


def repoint_feeder(node, new_number=None, *, actor, now=None) -> ManagedNodeIdentityEvent:
    """Re-point a Meshtastic feeder at ``new_number`` (default: the number its bot last reported) by hand.

    A person is deciding, so ``MESHTASTIC_FEEDER_AUTO_REKEY`` is not consulted. An owner may only move a feeder to the
    number it last reported, and only when crc32 of its trusted stored key gives that number; any other number,
    reversing a re-key included, is staff only. An owner is also refused a target with a different key or belonging to
    someone else, as the automatic re-key is. An existing ``ObservedNode`` is never claimed here, and a missing one
    is created unclaimed. Staff take the stored key from the newest open flagged event when that event's number
    matches; an owner's re-point keeps the stored key. Raises ``FeederRepointError``. The manual event (and the
    flagged rows it resolves) are acknowledged by ``actor``.
    """
    if node.protocol != Protocol.MESHTASTIC:
        raise FeederRepointError(FeederRepointError.CODE_NOT_MESHTASTIC, "Only Meshtastic feeders have a node number.")
    if new_number is None:
        new_number = node.reported_meshtastic_node_id
        if new_number is None:
            raise FeederRepointError(
                FeederRepointError.CODE_NO_REPORTED_NUMBER, "This feeder has not reported a node number."
            )
    if not _valid_node_number(new_number):
        raise FeederRepointError(FeederRepointError.CODE_INVALID_NODE_ID, "Not a valid Meshtastic node number.")
    now = now or timezone.now()

    collision = FeederRepointError(FeederRepointError.CODE_NUMBER_COLLISION, "Another feeder already has that number.")
    try:
        with transaction.atomic():
            locked = _lock(node)
            old_num = locked.meshtastic_node_id
            if old_num == new_number:
                raise FeederRepointError(
                    FeederRepointError.CODE_ALREADY_CURRENT, "The feeder already has that node number."
                )
            if not actor.is_staff and not _owner_may_repoint(locked, new_number, now):
                raise FeederRepointError(
                    FeederRepointError.CODE_NOT_PROVEN,
                    "Only the number this feeder reports, proved by its stored public key, can be set without staff.",
                )
            if _number_held_by_another_feeder(locked, new_number):
                raise collision
            if not actor.is_staff:
                _check_owner_target(locked, new_number)
            open_flagged = list(_open_flagged(locked).order_by("-created_at", "-id"))
            matching = next((row for row in open_flagged if row.new_meshtastic_node_id == new_number), None)
            key_hex = normalise_pubkey(matching.reported_public_key) if matching else None
            if not actor.is_staff:
                # The proof above rests on the stored key; a flagged report must not replace it.
                key_hex = normalise_pubkey(locked.meshtastic_public_key)
            fields = ["meshtastic_node_id"]
            locked.meshtastic_node_id = new_number
            if key_hex is not None:
                locked.meshtastic_public_key = key_hex
                locked.meshtastic_key_node_id = key_node_id(key_hex)
                fields += ["meshtastic_public_key", "meshtastic_key_node_id"]
            locked.save(update_fields=fields)
            seen = {"acknowledged_at": now, "acknowledged_by": actor}
            ManagedNodeIdentityEvent.objects.filter(pk__in=[row.pk for row in open_flagged]).update(
                resolved_at=now, **seen
            )
            event = ManagedNodeIdentityEvent.objects.create(
                managed_node=locked,
                old_meshtastic_node_id=old_num,
                new_meshtastic_node_id=new_number,
                reported_public_key=key_hex,
                outcome=Outcome.MANUAL,
                resolved_at=now,
                **seen,
            )
    except IntegrityError:
        raise collision from None

    for name in fields:
        setattr(node, name, getattr(locked, name))
    _count(Outcome.MANUAL)
    logger.info(
        "Feeder %s (%s) re-pointed by user %s: %s -> %s",
        node.internal_id,
        node.name,
        getattr(actor, "pk", None),
        meshtastic_id_to_hex(old_num),
        meshtastic_id_to_hex(new_number),
    )
    _after_commit(node, event, old_num, new_number, claim=False)
    return event


def _after_commit(node, event, old_num, new_num, *, claim) -> None:
    """The number has changed and committed: nothing here may turn that into a failure for the caller."""
    try:
        ensure_observed_node_for_managed_node(node, claim=claim)
    except Exception:
        logger.exception("Feeder %s: could not ensure ObservedNode after re-point", node.internal_id)
    for receiver, result in feeder_identity_changed.send_robust(
        sender=ManagedNode, managed_node=node, event=event, old_node_id=old_num, new_node_id=new_num
    ):
        if isinstance(result, Exception):
            logger.error(
                "Feeder %s: identity signal receiver %r failed: %r",
                node.internal_id,
                receiver,
                result,
                exc_info=result,
            )


def accept_reported_key(node, *, actor, now=None) -> ManagedNodeIdentityEvent:
    """Staff accept the key a feeder reports for its unchanged number (the 2.7 key-regeneration case).

    A report never replaces a stored key, so a re-keyed radio that keeps its number stays ``key_mismatch`` for ever.
    The key comes from the newest open ``key_mismatch`` row for the current number (never from the request), so
    staff accept what the feeder actually reported. Owners can't: their re-point proof rests on the stored key. Writes
    a ``key_accepted`` event and resolves the open flagged rows, all acknowledged by ``actor``; the number is
    unchanged, so there is no signal. Raises ``FeederRepointError``.
    """
    if node.protocol != Protocol.MESHTASTIC:
        raise FeederRepointError(FeederRepointError.CODE_NOT_MESHTASTIC, "Only Meshtastic feeders have a node number.")
    if not actor.is_staff:
        raise FeederRepointError(FeederRepointError.CODE_STAFF_ONLY, "Only staff can accept a new public key.")
    now = now or timezone.now()
    with transaction.atomic():
        locked = _lock(node)
        number = locked.meshtastic_node_id
        open_flagged = list(_open_flagged(locked).order_by("-created_at", "-id"))
        matching = next(
            (
                row
                for row in open_flagged
                if row.reason == Reason.KEY_MISMATCH
                and row.new_meshtastic_node_id == number
                and normalise_pubkey(row.reported_public_key) is not None
            ),
            None,
        )
        if matching is None:
            raise FeederRepointError(
                FeederRepointError.CODE_NO_KEY_TO_ACCEPT,
                "This feeder has no reported public key waiting to be accepted.",
            )
        key_hex = normalise_pubkey(matching.reported_public_key)
        locked.meshtastic_public_key = key_hex
        locked.meshtastic_key_node_id = key_node_id(key_hex)
        locked.save(update_fields=["meshtastic_public_key", "meshtastic_key_node_id"])
        seen = {"acknowledged_at": now, "acknowledged_by": actor}
        ManagedNodeIdentityEvent.objects.filter(pk__in=[row.pk for row in open_flagged]).update(resolved_at=now, **seen)
        event = ManagedNodeIdentityEvent.objects.create(
            managed_node=locked,
            old_meshtastic_node_id=number,
            new_meshtastic_node_id=number,
            reported_public_key=key_hex,
            outcome=Outcome.KEY_ACCEPTED,
            resolved_at=now,
            **seen,
        )
    node.meshtastic_public_key = locked.meshtastic_public_key
    node.meshtastic_key_node_id = locked.meshtastic_key_node_id
    _count(Outcome.KEY_ACCEPTED)
    logger.info(
        "Feeder %s (%s): user %s accepted the reported public key for %s",
        node.internal_id,
        node.name,
        getattr(actor, "pk", None),
        meshtastic_id_to_hex(number),
    )
    return event
