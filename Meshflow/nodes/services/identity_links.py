"""Record that two Meshtastic ``ObservedNode`` rows are the same radio (ADR-0006, step 2).

In 2.8 a node's number is ``crc32(public key)``, so an upgraded radio shows up under a new number as a new row and the
old row goes quiet. This module records one ``ObservedNodeIdentityLink`` from the old row to the new one. Rows are never
merged and no packet's ``from_int`` is rewritten; rolling back is deleting link rows.

Evidence, strongest first:

* **public key** -- the node's number is the crc32 of its key and exactly one other row holds the key: ``auto``.
  A key held by more than one candidate is a cloned key and can never be linked: one ``flagged`` row names every holder.
* **managed feeder re-key** -- the feeder re-key service moved a feeder's number: ``auto`` (automatic) or
  ``confirmed`` (a person did it).
* **MAC** (on-air NodeInfo only; NodeDB uploads zero other nodes' MACs on 2.8): a row numbered by the MAC's last four
  bytes, or holding the same MAC, whose key differs: ``suggested``, medium confidence, never promoted by MAC alone.

Everything here is idempotent. The ``detect_*`` entry points called from ingest and the signal receiver **never raise**:
a failure is logged and the caller carries on. A ``rejected`` row is never recreated or promoted, and the reverse of an
existing pair is never created. A second live successor of one old row (or predecessor of one new row) is refused by
the database; that is logged and ingest continues.
"""

from __future__ import annotations

import logging
from enum import Enum

from django.db import IntegrityError, transaction
from django.db.models import Q

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import is_blank_mac, key_node_id, mac_node_number
from common.protocol import Protocol
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.signals import identity_link_live

logger = logging.getLogger(__name__)

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence
Confidence = Link.Confidence

# A state only ever moves up this ladder (rejected is outside it: it is never promoted).
_RANK = {State.SUGGESTED: 1, State.AUTO: 2, State.CONFIRMED: 3}


class Outcome(str, Enum):
    NONE = "none"  # nothing to record
    CREATED = "created"
    PROMOTED = "promoted"
    UNCHANGED = "unchanged"
    REJECTED = "rejected"  # a rejected row exists for the pair; left alone
    REVERSE = "reverse"  # the reverse pair exists; never create the opposite link
    CONFLICT = "conflict"  # the database refused a second live successor/predecessor
    FLAGGED_CREATED = "flagged_created"
    FLAGGED_UPDATED = "flagged_updated"
    FLAGGED_UNCHANGED = "flagged_unchanged"

    @property
    def flagged(self) -> bool:
        return self in (Outcome.FLAGGED_CREATED, Outcome.FLAGGED_UPDATED, Outcome.FLAGGED_UNCHANGED)


def send_live(link: ObservedNodeIdentityLink) -> None:
    """Tell listeners a link became ``auto`` or ``confirmed``, once the surrounding transaction commits."""

    def send():
        for receiver, result in identity_link_live.send_robust(sender=Link, link=link):
            if isinstance(result, Exception):
                logger.error("Identity link signal receiver %r failed: %r", receiver, result)

    transaction.on_commit(send)


def _holder_detail(node: ObservedNode) -> dict:
    number = node.meshtastic_node_id
    return {"node_id": number, "node_id_str": meshtastic_id_to_hex(number)}


def record_link(
    old: ObservedNode,
    new: ObservedNode,
    *,
    evidence: str,
    confidence: str,
    state: str,
    public_key_hex: str | None = None,
    detail: dict | None = None,
    reviewer=None,
) -> Outcome:
    """Create the link ``old -> new`` or fold this evidence into the one that exists.

    A new state only replaces an existing one when it ranks higher (suggested < auto < confirmed); a rejected row is
    never touched. When evidence replaces a suggestion the earlier evidence is kept under ``detail["earlier"]``;
    otherwise extra evidence for a live link is noted under ``detail["also"]``.
    """
    if old.pk == new.pk:
        return Outcome.NONE
    existing = Link.objects.filter(old_node=old, new_node=new).first()
    if existing is not None:
        return _fold(existing, evidence, confidence, state, public_key_hex, reviewer)
    if Link.objects.filter(old_node=new, new_node=old).exists():
        return Outcome.REVERSE
    try:
        with transaction.atomic():
            link = Link.objects.create(
                old_node=old,
                new_node=new,
                evidence=evidence,
                confidence=confidence,
                state=state,
                public_key_hex=public_key_hex,
                detail=detail or {},
                reviewed_by=reviewer if state == State.CONFIRMED else None,
            )
    except IntegrityError:
        logger.warning(
            "Identity link %s -> %s (%s, %s) refused: a live link already uses one of the nodes",
            meshtastic_id_to_hex(old.meshtastic_node_id),
            meshtastic_id_to_hex(new.meshtastic_node_id),
            evidence,
            state,
        )
        return Outcome.CONFLICT
    if state in Link.LIVE_STATES:
        send_live(link)
    return Outcome.CREATED


def _fold(existing, evidence, confidence, state, public_key_hex, reviewer) -> Outcome:
    """Fold new evidence into an existing link: states only move up, a rejected row is never touched."""
    if existing.state == State.REJECTED:
        return Outcome.REJECTED
    detail = dict(existing.detail)
    also = list(detail.get("also", []))
    if _RANK.get(state, 0) <= _RANK.get(existing.state, 0):
        if evidence != existing.evidence and evidence not in also:
            detail["also"] = [*also, evidence]
            existing.detail = detail
            existing.save(update_fields=["detail", "updated_at"])
        return Outcome.UNCHANGED
    was_live = existing.state in Link.LIVE_STATES
    if existing.evidence == Evidence.MAC and evidence != Evidence.MAC:
        detail["earlier"] = existing.evidence  # a MAC suggestion promoted by stronger evidence
        existing.evidence, existing.confidence = evidence, confidence
    elif evidence != existing.evidence and evidence not in also:
        detail["also"] = [*also, evidence]
    existing.state = state
    existing.detail = detail
    if public_key_hex and not existing.public_key_hex:
        existing.public_key_hex = public_key_hex
    if state == State.CONFIRMED and reviewer is not None:
        existing.reviewed_by = reviewer
    try:
        with transaction.atomic():
            existing.save()
    except IntegrityError:
        logger.warning(
            "Identity link %s could not become %s: a live link already uses one of its nodes", existing.pk, state
        )
        return Outcome.CONFLICT
    if not was_live and state in Link.LIVE_STATES:
        send_live(existing)
    return Outcome.PROMOTED


def _flag_key(key_hex: str, holders: list[ObservedNode]) -> Outcome:
    """One ``flagged`` row for a key held by several nodes, naming every holder. Never a link."""
    detail = {"holders": sorted((_holder_detail(h) for h in holders), key=lambda h: h["node_id"])}
    existing = Link.objects.filter(state=State.FLAGGED, public_key_hex=key_hex).first()
    if existing is not None:
        if existing.detail == detail:
            return Outcome.FLAGGED_UNCHANGED
        existing.detail = detail
        existing.save(update_fields=["detail", "updated_at"])
        return Outcome.FLAGGED_UPDATED
    try:
        with transaction.atomic():
            Link.objects.create(
                evidence=Evidence.PUBLIC_KEY,
                confidence=Confidence.STRONG,
                state=State.FLAGGED,
                public_key_hex=key_hex,
                detail=detail,
            )
    except IntegrityError:
        return Outcome.FLAGGED_UNCHANGED  # another worker flagged it first
    return Outcome.FLAGGED_CREATED


def _key_holders(key_hex: str) -> list[ObservedNode]:
    return list(
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_public_key_hex=key_hex)
        .only("internal_id", "meshtastic_node_id", "meshtastic_key_node_id")
        .order_by("pk")
    )


def evaluate_holders(key_hex: str, holders: list[ObservedNode]) -> Outcome:
    """Decide what the holders of one key mean: a link, a flag, or nothing."""
    if len(holders) < 2:
        return Outcome.NONE
    predicted = key_node_id(key_hex)
    numbered_by_key = [h for h in holders if h.meshtastic_node_id == predicted]
    if len(holders) == 2 and len(numbered_by_key) == 1:
        new = numbered_by_key[0]
        old = next(h for h in holders if h.pk != new.pk)
        outcome = record_link(
            old,
            new,
            evidence=Evidence.PUBLIC_KEY,
            confidence=Confidence.STRONG,
            state=State.AUTO,
            public_key_hex=key_hex,
        )
        if outcome != Outcome.CONFLICT:
            Link.objects.filter(state=State.FLAGGED, public_key_hex=key_hex).delete()  # it is linkable now
        return outcome
    _retire_shared_key_links(key_hex)
    return _flag_key(key_hex, holders)


def _retire_shared_key_links(key_hex: str) -> None:
    """A key that has become shared is no evidence of one device: drop its ``auto`` key links to ``suggested``.

    The row and its history stay, but it leaves the live set. ``confirmed`` (staff) links are left alone, and so
    is any link whose evidence is not the key itself (a feeder re-key stays live).
    """
    for link in Link.objects.filter(state=State.AUTO, evidence=Evidence.PUBLIC_KEY, public_key_hex=key_hex):
        link.state = State.SUGGESTED
        link.detail = {**link.detail, "key_now_shared": True}
        link.save(update_fields=["state", "detail", "updated_at"])


def evaluate_key(key_hex: str) -> Outcome:
    """Evaluate every holder of ``key_hex`` (used by the command)."""
    return evaluate_holders(key_hex, _key_holders(key_hex))


def _mac_candidates(node: ObservedNode, mac: str, tail: int | None) -> list[ObservedNode]:
    match = Q(mac_addr=mac)
    if tail is not None and tail != node.meshtastic_node_id:
        match |= Q(meshtastic_node_id=tail)
    rows = ObservedNode.objects.filter(match, protocol=Protocol.MESHTASTIC).exclude(pk=node.pk)
    return [
        row
        for row in rows
        if not (node.meshtastic_public_key_hex and row.meshtastic_public_key_hex == node.meshtastic_public_key_hex)
    ]


def _numbered_by_own_key(node: ObservedNode) -> bool:
    return node.meshtastic_key_node_id is not None and node.meshtastic_key_node_id == node.meshtastic_node_id


def link_by_mac(node: ObservedNode, mac: str | None) -> Outcome:
    """Suggest a link from an on-air NodeInfo MAC. Two candidates, or none, record nothing."""
    if is_blank_mac(mac):
        return Outcome.NONE
    if Link.objects.filter(Q(old_node=node) | Q(new_node=node)).exists():
        return Outcome.NONE  # already part of a link (any state): no MAC work due
    tail = mac_node_number(mac)
    candidates = _mac_candidates(node, mac, tail)
    if len(candidates) != 1:
        return Outcome.NONE
    other = candidates[0]
    if tail is not None and other.meshtastic_node_id == tail:
        old, new = other, node
    elif _numbered_by_own_key(node) and not _numbered_by_own_key(other):
        old, new = other, node
    elif _numbered_by_own_key(other) and not _numbered_by_own_key(node):
        old, new = node, other
    else:
        return Outcome.NONE
    return record_link(
        old,
        new,
        evidence=Evidence.MAC,
        confidence=Confidence.MEDIUM,
        state=State.SUGGESTED,
        detail={"mac": mac},
    )


def link_feeder_rekey(old_number: int, new_number: int, *, manual: bool, reviewer=None) -> Outcome:
    """Link a re-keyed feeder's old row to its new one (merging with an existing key link)."""
    rows = {
        row.meshtastic_node_id: row
        for row in ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC, meshtastic_node_id__in=[old_number, new_number]
        )
    }
    old, new = rows.get(old_number), rows.get(new_number)
    if old is None or new is None:
        return Outcome.NONE
    return record_link(
        old,
        new,
        evidence=Evidence.FEEDER_REKEY,
        confidence=Confidence.STRONG,
        state=State.CONFIRMED if manual else State.AUTO,
        public_key_hex=new.meshtastic_public_key_hex,
        reviewer=reviewer,
    )


# --- Entry points for ingest and signals: never raise -------------------------------------------------------


def detect_after_key_write(node: ObservedNode) -> Outcome:
    """After a node's key was written: link or flag. One query when there is no work. Never raises."""
    try:
        key_hex = node.meshtastic_public_key_hex
        if not key_hex or node.protocol != Protocol.MESHTASTIC:
            return Outcome.NONE
        holders = _key_holders(key_hex)
        if len(holders) < 2:
            return Outcome.NONE
        return evaluate_holders(key_hex, holders)
    except Exception:
        logger.exception("Identity link detection failed for node %s", getattr(node, "meshtastic_node_id", None))
        return Outcome.NONE


def detect_after_nodeinfo(node: ObservedNode, mac: str | None, *, key_written: bool) -> Outcome:
    """After an on-air NodeInfo: key evidence when the key was written, then MAC evidence. Never raises."""
    outcome = Outcome.NONE
    if key_written:
        outcome = detect_after_key_write(node)
    try:
        if outcome in (Outcome.NONE, Outcome.UNCHANGED) and not is_blank_mac(mac):
            outcome = link_by_mac(node, mac)
    except Exception:
        logger.exception("Identity link MAC detection failed for node %s", getattr(node, "meshtastic_node_id", None))
    return outcome


def detect_after_feeder_rekey(old_number: int, new_number: int, *, manual: bool, reviewer=None) -> Outcome:
    """Receiver body for ``feeder_identity_changed``. Never raises."""
    try:
        return link_feeder_rekey(old_number, new_number, manual=manual, reviewer=reviewer)
    except Exception:
        logger.exception("Identity link from feeder re-key %s -> %s failed", old_number, new_number)
        return Outcome.NONE
