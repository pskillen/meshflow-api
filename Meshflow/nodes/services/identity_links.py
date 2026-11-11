"""Record that two Meshtastic ``ObservedNode`` rows are the same radio (ADR-0006, step 2).

In 2.8 a node's number is ``crc32(public key)``, so an upgraded radio shows up under a new number as a new row and the
old row goes quiet. This module records one ``ObservedNodeIdentityLink`` from the old row to the new one. Rows are never
merged and no packet's ``from_int`` is rewritten; rolling back is deleting link rows.

Evidence, strongest first:

* **public key** -- the node's number is the crc32 of its key and exactly one other row holds the key: ``auto``.
  A key held by more than one candidate is a cloned key and can never be linked: one ``flagged`` row names every holder.
* **managed feeder re-key** -- the feeder re-key service moved a feeder's number: ``auto`` (automatic) or
  ``confirmed`` (a person did it).
* **predicted number** -- a row with no stored key whose number is the one an older row's key predicts
  (``meshtastic_key_node_id``), when that key is held by nothing else: ``auto``, medium, made at the new row's first
  packet. Key evidence replaces it; a different key demotes it to ``suggested``.
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
from django.utils import timezone

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import is_blank_mac, key_node_id, mac_node_number
from common.protocol import Protocol
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services.identity_chain import reaches
from nodes.signals import identity_link_live

logger = logging.getLogger(__name__)

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence
Confidence = Link.Confidence

# A state only ever moves up this ladder (rejected is outside it: it is never promoted).
_RANK = {State.SUGGESTED: 1, State.AUTO: 2, State.CONFIRMED: 3}

# Evidence that only hints at the pair, and the evidence that supersedes it when it arrives.
_HINT_EVIDENCE = (Evidence.MAC, Evidence.PREDICTED_NUMBER)
_STRONGER_EVIDENCE = (Evidence.PUBLIC_KEY, Evidence.FEEDER_REKEY, Evidence.DECLARED)


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
    never touched. Stronger evidence (key, feeder re-key, declared) replaces a MAC or predicted-number link's evidence
    even at an equal state, the earlier evidence kept under ``detail["earlier"]``; otherwise extra evidence for a live
    link is noted under ``detail["also"]``.
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
    supersedes = existing.evidence in _HINT_EVIDENCE and evidence in _STRONGER_EVIDENCE
    if not supersedes and _RANK.get(state, 0) <= _RANK.get(existing.state, 0):
        if evidence != existing.evidence and evidence not in also:
            detail["also"] = [*also, evidence]
            existing.detail = detail
            existing.save(update_fields=["detail", "updated_at"])
        return Outcome.UNCHANGED
    was_live = existing.state in Link.LIVE_STATES
    if supersedes:
        detail["earlier"] = existing.evidence  # a MAC or predicted-number hint replaced by stronger evidence
        existing.evidence, existing.confidence = evidence, confidence
    elif evidence != existing.evidence and evidence not in also:
        detail["also"] = [*also, evidence]
    if _RANK.get(state, 0) > _RANK.get(existing.state, 0):
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

    A predicted-number link rests on the old row's key too, so it goes the same way.

    The row and its history stay, but it leaves the live set. ``confirmed`` (staff) links are left alone, and so
    is any link whose evidence is not the key itself (a feeder re-key stays live).
    """
    for link in Link.objects.filter(
        state=State.AUTO, evidence__in=[Evidence.PUBLIC_KEY, Evidence.PREDICTED_NUMBER], public_key_hex=key_hex
    ):
        link.state = State.SUGGESTED
        link.detail = {**link.detail, "key_now_shared": True}
        link.save(update_fields=["state", "detail", "updated_at"])


def _demote_predicted_if_key_differs(node: ObservedNode, key_hex: str) -> None:
    """``node`` learned its key: an ``auto`` predicted-number link that rests on another key was wrong.

    An explicit exception to "states only move up" (like ``_retire_shared_key_links``): the link stays as a
    ``suggested`` row with ``detail["key_differs"]``. A ``confirmed`` link is a person's decision and is left alone.
    """
    for link in Link.objects.filter(new_node=node, evidence=Evidence.PREDICTED_NUMBER, state=State.AUTO).exclude(
        public_key_hex=key_hex
    ):
        link.state = State.SUGGESTED
        link.detail = {**link.detail, "key_differs": True}
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


def link_by_prediction(node: ObservedNode) -> Outcome:
    """Link ``node`` to the one row whose key predicted its number, at the node's first packet.

    Records nothing unless ``node`` has no stored key, exactly one other row predicted its number from a stored key
    that gives that row a different number, and that key is held by that row alone and is not flagged.
    """
    if node.protocol != Protocol.MESHTASTIC or node.meshtastic_node_id is None or node.meshtastic_public_key_hex:
        return Outcome.NONE
    candidates = [
        row
        for row in ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC,
            meshtastic_key_node_id=node.meshtastic_node_id,
            meshtastic_public_key_hex__isnull=False,
        )
        .exclude(pk=node.pk)
        .exclude(meshtastic_node_id=node.meshtastic_node_id)
        .order_by("pk")[:2]
    ]
    if len(candidates) != 1:
        return Outcome.NONE
    old = candidates[0]
    old_key = old.meshtastic_public_key_hex
    if [h.pk for h in _key_holders(old_key)] != [old.pk]:
        return Outcome.NONE
    if Link.objects.filter(state=State.FLAGGED, public_key_hex=old_key).exists():
        return Outcome.NONE
    return record_link(
        old,
        node,
        evidence=Evidence.PREDICTED_NUMBER,
        confidence=Confidence.MEDIUM,
        state=State.AUTO,
        public_key_hex=old_key,
        detail={"predicted_from": old.node_id_str},
    )


def link_feeder_rekey(
    old_number: int, new_number: int, *, manual: bool, reviewer=None, event_id: int | None = None
) -> Outcome:
    """Link a re-keyed feeder's old row to its new one (merging with an existing key link).

    ``event_id`` is the ``ManagedNodeIdentityEvent`` that moved the feeder; it is recorded as
    ``detail["feeder_event_id"]`` on a new link, and added to an existing link that lacks it (nothing else changes).
    """
    rows = {
        row.meshtastic_node_id: row
        for row in ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC, meshtastic_node_id__in=[old_number, new_number]
        )
    }
    old, new = rows.get(old_number), rows.get(new_number)
    if old is None or new is None:
        return Outcome.NONE
    outcome = record_link(
        old,
        new,
        evidence=Evidence.FEEDER_REKEY,
        confidence=Confidence.STRONG,
        state=State.CONFIRMED if manual else State.AUTO,
        public_key_hex=new.meshtastic_public_key_hex,
        detail={"feeder_event_id": event_id} if event_id is not None else None,
        reviewer=reviewer,
    )
    if event_id is not None:
        _note_feeder_event(old, new, event_id)
    return outcome


def _note_feeder_event(old: ObservedNode, new: ObservedNode, event_id: int) -> None:
    """Add ``feeder_event_id`` to an existing, non-rejected link that does not carry it yet."""
    link = Link.objects.filter(old_node=old, new_node=new).exclude(state=State.REJECTED).first()
    if link is not None and "feeder_event_id" not in link.detail:
        link.detail = {**link.detail, "feeder_event_id": event_id}
        link.save(update_fields=["detail", "updated_at"])


# --- Entry points for ingest and signals: never raise -------------------------------------------------------


def detect_after_key_write(node: ObservedNode) -> Outcome:
    """After a node's key was written: link or flag. One query when there is no work. Never raises."""
    try:
        key_hex = node.meshtastic_public_key_hex
        if not key_hex or node.protocol != Protocol.MESHTASTIC:
            return Outcome.NONE
        _demote_predicted_if_key_differs(node, key_hex)
        holders = _key_holders(key_hex)
        if len(holders) < 2:
            return Outcome.NONE
        return evaluate_holders(key_hex, holders)
    except Exception:
        logger.exception("Identity link detection failed for node %s", getattr(node, "meshtastic_node_id", None))
        return Outcome.NONE


def detect_at_first_packet(node: ObservedNode) -> Outcome:
    """After a new row was created from a packet: link it when its number was predicted. Never raises."""
    try:
        return link_by_prediction(node)
    except Exception:
        logger.exception("Identity link prediction failed for node %s", getattr(node, "meshtastic_node_id", None))
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


def detect_after_feeder_rekey(
    old_number: int, new_number: int, *, manual: bool, reviewer=None, event_id: int | None = None
) -> Outcome:
    """Receiver body for ``feeder_identity_changed``. Never raises."""
    try:
        return link_feeder_rekey(old_number, new_number, manual=manual, reviewer=reviewer, event_id=event_id)
    except Exception:
        logger.exception("Identity link from feeder re-key %s -> %s failed", old_number, new_number)
        return Outcome.NONE


# --- Review by people: one path for the admin and the API ---------------------------------------------------


class IdentityLinkError(Exception):
    """A review action was refused; ``code`` is one of the ``CODE_*`` values (the API's ``code`` field)."""

    CODE_LINK_CONFLICT = "link_conflict"
    CODE_NOT_OWNER = "not_owner"
    CODE_CROSS_PROTOCOL = "cross_protocol"
    CODE_SAME_NODE = "same_node"
    CODE_INVALID_STATE = "invalid_state"
    CODE_NOT_FOUND = "not_found"
    CODE_AMBIGUOUS = "ambiguous_node"
    CODE_CYCLE = "link_cycle"

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# HTTP status for each refusal; any code not listed is a 400.
IDENTITY_LINK_HTTP_STATUS = {
    IdentityLinkError.CODE_LINK_CONFLICT: 409,
    IdentityLinkError.CODE_NOT_OWNER: 403,
    IdentityLinkError.CODE_INVALID_STATE: 409,
    IdentityLinkError.CODE_NOT_FOUND: 404,
    IdentityLinkError.CODE_CYCLE: 409,
}


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


def _owns(user, node: ObservedNode) -> bool:
    return bool(user and user.is_authenticated and node.claimed_by_id == user.pk)


def _free_for(user, node: ObservedNode) -> bool:
    """The node is the user's or nobody's."""
    return node.claimed_by_id is None or node.claimed_by_id == user.pk


def can_see_link(user, link: ObservedNodeIdentityLink) -> bool:
    """Live links are public; ``suggested`` and ``rejected`` go to either row's owner and staff; never ``flagged``."""
    if link.state == State.FLAGGED or link.old_node_id is None:
        return False
    if link.state in Link.LIVE_STATES:
        return True
    return _is_staff(user) or _owns(user, link.old_node) or _owns(user, link.new_node)


def may_review_link(user, link: ObservedNodeIdentityLink) -> bool:
    """Who may act on a link at all, whatever its state: staff, or an owner of one row (see ``can_confirm``)."""
    return _is_staff(user) or _owns(user, link.old_node) or _owns(user, link.new_node)


def can_confirm_link(user, link: ObservedNodeIdentityLink) -> bool:
    """Staff, or the owner of one row when the other is theirs or unclaimed; only for a ``suggested`` link."""
    if link.state != State.SUGGESTED or link.old_node_id is None:
        return False
    if _is_staff(user):
        return True
    return (_owns(user, link.old_node) and _free_for(user, link.new_node)) or (
        _owns(user, link.new_node) and _free_for(user, link.old_node)
    )


def can_reject_link(user, link: ObservedNodeIdentityLink) -> bool:
    """Staff, or the owner of either row; any state but ``rejected`` and ``flagged``."""
    if link.state in (State.REJECTED, State.FLAGGED) or link.old_node_id is None:
        return False
    return may_review_link(user, link)


def may_declare_from(user, old: ObservedNode) -> bool:
    """The cheap half of :func:`can_declare_link`: staff, or the owner of ``old`` (declaring needs it)."""
    return _is_staff(user) or _owns(user, old)


def can_declare_link(user, old: ObservedNode, new: ObservedNode) -> bool:
    """Staff (any pair), or someone who owns both rows."""
    return _is_staff(user) or (_owns(user, old) and _owns(user, new))


def _lock_nodes(*nodes: ObservedNode) -> None:
    """Row-lock the nodes in pk order (one order everywhere, so two writers cannot deadlock). Call inside a transaction.

    Two people linking the same nodes at once (A -> B and B -> A) take turns here, so the second one sees the first's
    link when it checks for a cycle. No-op on SQLite.
    """
    pks = sorted({node.pk for node in nodes})
    list(ObservedNode.objects.select_for_update().filter(pk__in=pks).order_by("pk").values_list("pk", flat=True))


def _refuse_cycle(old: ObservedNode, new: ObservedNode) -> None:
    """Refuse a live link ``old -> new`` when ``new`` already reaches ``old`` through live links."""
    if reaches(new, old):
        raise IdentityLinkError(
            IdentityLinkError.CODE_CYCLE,
            "That would make the nodes replace each other in a loop; reject the other link.",
        )


def set_link_state(
    link: ObservedNodeIdentityLink, state: str, actor, *, allowed_from: tuple[str, ...] | None = None
) -> ObservedNodeIdentityLink:
    """Move a link to ``state``: stamp the reviewer, save atomically, tell listeners when it became live.

    The one write path for the admin and the API (permissions are the caller's). The row is locked and its current
    state re-read first, so a stale object cannot resurrect a link someone else has just moved. ``allowed_from``, when
    given, lists the states the locked row may be in (the API's confirm and reject use it); the admin passes none and
    may move a link between any two states. A ``flagged`` row is never changed. Making a link live is refused with
    ``link_cycle`` when the new node already reaches the old one through live links, and a second live link on either
    node is refused by the database and raised as ``link_conflict``.
    """
    if state not in State.values or state == State.FLAGGED:
        raise IdentityLinkError(IdentityLinkError.CODE_INVALID_STATE, f"Cannot set a link to {state!r}.")
    if link.old_node_id is None:
        raise IdentityLinkError(IdentityLinkError.CODE_INVALID_STATE, "A flagged row is not a link.")
    previous = link.state
    try:
        with transaction.atomic():
            _lock_nodes(link.old_node, link.new_node)
            locked = Link.objects.select_for_update().select_related("old_node", "new_node").get(pk=link.pk)
            previous = locked.state
            if previous == State.FLAGGED:
                raise IdentityLinkError(IdentityLinkError.CODE_INVALID_STATE, "A flagged row is not a link.")
            if allowed_from is not None and previous not in allowed_from:
                raise IdentityLinkError(
                    IdentityLinkError.CODE_INVALID_STATE, f"The link is {previous}; that is not allowed from there."
                )
            if previous == state:
                return locked
            becomes_live = state in Link.LIVE_STATES and previous not in Link.LIVE_STATES
            if becomes_live:
                _refuse_cycle(locked.old_node, locked.new_node)
            locked.state = state
            locked.reviewed_by = actor
            locked.reviewed_at = timezone.now()
            locked.save()
            if becomes_live:
                send_live(locked)
    except IntegrityError:
        link.state = previous
        raise IdentityLinkError(
            IdentityLinkError.CODE_LINK_CONFLICT,
            "Another live link already uses the old or new node; change that one first.",
        )
    link.state, link.reviewed_by, link.reviewed_at = locked.state, locked.reviewed_by, locked.reviewed_at
    return locked


def confirm_link(link: ObservedNodeIdentityLink, actor) -> ObservedNodeIdentityLink:
    """``suggested`` -> ``confirmed``, checked on the locked row."""
    return set_link_state(link, State.CONFIRMED, actor, allowed_from=(State.SUGGESTED,))


def reject_link(link: ObservedNodeIdentityLink, actor) -> ObservedNodeIdentityLink:
    """``suggested``, ``auto`` or ``confirmed`` -> ``rejected``; a rejected or flagged row is refused."""
    return set_link_state(link, State.REJECTED, actor, allowed_from=(State.SUGGESTED, State.AUTO, State.CONFIRMED))


def declare_link(old: ObservedNode, new: ObservedNode, actor) -> ObservedNodeIdentityLink:
    """Record that a person says ``new`` replaced ``old``: ``declared`` evidence, strong, ``confirmed``."""
    return declare_link_changed(old, new, actor)[0]


def declare_link_changed(old: ObservedNode, new: ObservedNode, actor) -> tuple[ObservedNodeIdentityLink, bool]:
    """:func:`declare_link`, also saying whether a link was created or promoted (``False``: nothing changed)."""
    if not can_declare_link(actor, old, new):
        raise IdentityLinkError(
            IdentityLinkError.CODE_NOT_OWNER, "You need to own both nodes to declare a replacement."
        )
    if old.pk == new.pk:
        raise IdentityLinkError(IdentityLinkError.CODE_SAME_NODE, "A node cannot replace itself.")
    if old.protocol != new.protocol:
        raise IdentityLinkError(IdentityLinkError.CODE_CROSS_PROTOCOL, "Both nodes must use the same protocol.")
    with transaction.atomic():
        _lock_nodes(old, new)
        before = Link.objects.filter(old_node=old, new_node=new).first()
        was_live = before is not None and before.state in Link.LIVE_STATES
        outcome = record_link(
            old, new, evidence=Evidence.DECLARED, confidence=Confidence.STRONG, state=State.CONFIRMED, reviewer=actor
        )
        if outcome == Outcome.REJECTED:
            raise IdentityLinkError(
                IdentityLinkError.CODE_LINK_CONFLICT, "This pair was rejected; staff can undo that in the admin."
            )
        if outcome in (Outcome.CONFLICT, Outcome.REVERSE, Outcome.NONE):
            raise IdentityLinkError(
                IdentityLinkError.CODE_LINK_CONFLICT,
                "Another live link, or the reverse link, already uses one of these nodes.",
            )
        if not was_live:
            _refuse_cycle(old, new)  # raising rolls the new or promoted row back
        link = Link.objects.get(old_node=old, new_node=new)
        changed = outcome in (Outcome.CREATED, Outcome.PROMOTED)
        if changed and link.state == State.CONFIRMED:
            link.reviewed_by, link.reviewed_at = actor, timezone.now()
            link.save(update_fields=["reviewed_by", "reviewed_at", "updated_at"])
    return link, changed
