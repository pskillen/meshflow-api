"""Read a node's other identities: the chain of ``ObservedNodeIdentityLink`` rows around it (ADR-0006).

This is the one place that reads chains; the API serializers and later work (monitoring, claims) import it. It never
writes anything.

* **Live states only** (``auto``, ``confirmed``). ``suggested``, ``rejected`` and ``flagged`` rows are ignored.
* The database allows one live successor per old node and one live predecessor per new node, so identities form chains
  A -> B -> C, never forks.
* ``chain(node)`` walks both ways, **nearest first**, one query per hop. Each walk stops after ``limit`` steps (default
  10) or at a node already seen (the start node is never included, nor a repeat), so a cycle built directly in the
  database terminates.
* **The replaced rule.** A node is *replaced* when it has a live successor S and either its ``last_heard`` is null or
  S has been heard at least as recently (S ``last_heard`` not null and ``>=`` the node's). An old row heard *after* its
  successor is not replaced: the link is still shown, but the old row is the live one.
* **A predicted-only link does not count.** A link whose evidence is ``predicted_number`` counts only once the new
  row's stored key equals the key the link rests on. Until then it is recorded and shown in the chain but never makes
  its old row *replaced*: a single forged packet carrying a node's predicted number must not hide a live node or pause
  its alerts. When the new row's key is heard, the link is superseded by key evidence (counts) or demoted (does not).
  :func:`link_counts` and
  :func:`counting_links_q` are the one definition; every consumer goes through them.
* **A successor is not new.** A row with a live predecessor link (:func:`has_live_predecessor`, any evidence, a
  ``predicted_number`` link whose key has not been heard yet included) is a successor. Callers use that to skip the
  noise a brand-new number would make: the baseline traceroute and the ``new_distant_node`` DX event. This is looser
  than the replaced rule on purpose: the replaced rule hides and pauses things, while here the only effect is skipping
  noise, and at a new number's first packet a predicted link is the only link there can be. A forged first packet
  costs one skipped baseline and one skipped ``new_distant_node`` event for the forged row. Read through the link,
  nothing is copied or written.
* :func:`replaced_by` returns the newest identity in the chain (the last ``next`` step); the list-side annotation
  (:func:`annotate_replaced_by`) names the direct successor, so that lists cost no extra queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Exists, F, OuterRef, Q, QuerySet, Subquery

from nodes.models import ObservedNode, ObservedNodeIdentityLink

Link = ObservedNodeIdentityLink

DEFAULT_LIMIT = 10


@dataclass
class ChainStep:
    """One hop: the far node and the link that joins it to the previous node in the walk."""

    node: ObservedNode
    link: ObservedNodeIdentityLink


@dataclass
class Chain:
    """The identities before (``previous``) and after (``next``) a node, nearest first."""

    previous: list[ChainStep] = field(default_factory=list)
    next: list[ChainStep] = field(default_factory=list)


def _walk(node: ObservedNode, *, forward: bool, limit: int) -> list[ChainStep]:
    near, far = ("old_node", "new_node") if forward else ("new_node", "old_node")
    steps: list[ChainStep] = []
    seen = {node.pk}
    current = node
    for _ in range(limit):
        link = (
            Link.objects.filter(**{near: current, "state__in": Link.LIVE_STATES})
            .select_related(far)
            .order_by("-created_at", "-pk")
            .first()
        )
        if link is None:
            break
        far_node = getattr(link, far)
        if far_node.pk in seen:
            break
        seen.add(far_node.pk)
        steps.append(ChainStep(node=far_node, link=link))
        current = far_node
    return steps


def chain(node: ObservedNode, *, limit: int = DEFAULT_LIMIT) -> Chain:
    """Walk live links back (``previous``) and forward (``next``) from ``node``: nearest first, ``limit`` each."""
    return Chain(
        previous=_walk(node, forward=False, limit=limit),
        next=_walk(node, forward=True, limit=limit),
    )


def has_live_predecessor(node: ObservedNode) -> bool:
    """Whether ``node`` is a successor: one ``EXISTS`` on its live predecessor links (see module docstring)."""
    return Link.objects.filter(new_node=node, state__in=Link.LIVE_STATES).exists()


def predecessors(node: ObservedNode, *, limit: int = DEFAULT_LIMIT) -> list[ObservedNode]:
    """The earlier identities of ``node``, nearest first (the ``previous`` walk). Never writes."""
    return [step.node for step in _walk(node, forward=False, limit=limit)]


def _norm_key(key: str | None) -> str:
    return (key or "").strip().lower()


def link_counts(link: ObservedNodeIdentityLink, successor: ObservedNode) -> bool:
    """Whether a live link may make its old row replaced: a predicted-number link needs the new row to hold its key."""
    if link.evidence != Link.Evidence.PREDICTED_NUMBER:
        return True
    link_key = _norm_key(link.public_key_hex)
    return bool(link_key) and link_key == _norm_key(successor.meshtastic_public_key_hex)


def counting_links_q() -> Q:
    """The queryset twin of :func:`link_counts`, on ``ObservedNodeIdentityLink`` (no extra join: ``new_node`` is
    already joined by the replaced rule). Stored keys are normalised lowercase hex, so equality is exact."""
    return ~Q(evidence=Link.Evidence.PREDICTED_NUMBER) | Q(new_node__meshtastic_public_key_hex=F("public_key_hex"))


def is_replaced_by(node: ObservedNode, successor: ObservedNode, link: ObservedNodeIdentityLink | None = None) -> bool:
    """The replaced rule for one pair (see module docstring). ``link`` is the live link between them, when known."""
    if link is not None and not link_counts(link, successor):
        return False
    if node.last_heard is None:
        return True
    return successor.last_heard is not None and successor.last_heard >= node.last_heard


def replaced_by(node: ObservedNode, chain_: Chain | None = None) -> ObservedNode | None:
    """The newest identity that replaces ``node``, or None. Pass an already-built ``chain_`` to avoid walking twice."""
    if chain_ is None:
        chain_ = chain(node)
    if not chain_.next:
        return None
    if not is_replaced_by(node, chain_.next[0].node, chain_.next[0].link):
        return None
    return chain_.next[-1].node


def _replaced_links() -> QuerySet:
    return (
        Link.objects.filter(old_node=OuterRef("pk"), state__in=Link.LIVE_STATES)
        .filter(counting_links_q())
        .filter(Q(old_node__last_heard__isnull=True) | Q(new_node__last_heard__gte=F("old_node__last_heard")))
    )


def replaced_q() -> Q:
    """A ``Q`` true for rows replaced by their direct successor; ``.exclude(replaced_q())`` drops them."""
    return Q(Exists(_replaced_links()))


def _successor_field(links: QuerySet, name: str) -> Subquery:
    field = ObservedNode._meta.get_field(name)
    return Subquery(links.values(f"new_node__{name}")[:1], output_field=field.clone())


def annotate_replaced_by(queryset: QuerySet) -> QuerySet:
    """Annotate the direct successor of replaced rows as ``replaced_by_*`` (null otherwise). No extra queries."""
    links = _replaced_links().order_by("-created_at", "-pk")
    return queryset.annotate(
        replaced_by_internal_id=_successor_field(links, "internal_id"),
        replaced_by_protocol=_successor_field(links, "protocol"),
        replaced_by_meshtastic_node_id=_successor_field(links, "meshtastic_node_id"),
        replaced_by_mc_pubkey=_successor_field(links, "mc_pubkey"),
        replaced_by_mc_pubkey_prefix=_successor_field(links, "mc_pubkey_prefix"),
    )


def annotate_replaced_by_m2m_opt_out(queryset: QuerySet) -> QuerySet:
    """Annotate ``replaced_by_m2m_opt_out``: the direct successor's M2M opt-out flag (null when not replaced)."""
    links = _replaced_links().order_by("-created_at", "-pk")
    return queryset.annotate(replaced_by_m2m_opt_out=_successor_field(links, "m2m_opt_out"))


def annotate_previous(queryset: QuerySet) -> QuerySet:
    """Annotate the direct live predecessor of rows as ``previous_*`` (null when none), plus ``previous_m2m_opt_out``.

    Unlike :func:`annotate_replaced_by` this ignores the replaced rule and the predicted-number rule: a row with a live
    predecessor link names it whether or not the old row is still the one heard. No extra queries.
    """
    links = Link.objects.filter(new_node=OuterRef("pk"), state__in=Link.LIVE_STATES).order_by("-created_at", "-pk")

    def _prev(name: str) -> Subquery:
        field = ObservedNode._meta.get_field(name)
        return Subquery(links.values(f"old_node__{name}")[:1], output_field=field.clone())

    return queryset.annotate(
        previous_protocol=_prev("protocol"),
        previous_meshtastic_node_id=_prev("meshtastic_node_id"),
        previous_mc_pubkey=_prev("mc_pubkey"),
        previous_mc_pubkey_prefix=_prev("mc_pubkey_prefix"),
        previous_m2m_opt_out=_prev("m2m_opt_out"),
    )
