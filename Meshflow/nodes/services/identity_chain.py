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


def is_replaced_by(node: ObservedNode, successor: ObservedNode) -> bool:
    """The replaced rule for one pair (see module docstring)."""
    if node.last_heard is None:
        return True
    return successor.last_heard is not None and successor.last_heard >= node.last_heard


def replaced_by(node: ObservedNode, chain_: Chain | None = None) -> ObservedNode | None:
    """The newest identity that replaces ``node``, or None. Pass an already-built ``chain_`` to avoid walking twice."""
    if chain_ is None:
        chain_ = chain(node)
    if not chain_.next:
        return None
    if not is_replaced_by(node, chain_.next[0].node):
        return None
    return chain_.next[-1].node


def _replaced_links() -> QuerySet:
    return Link.objects.filter(old_node=OuterRef("pk"), state__in=Link.LIVE_STATES).filter(
        Q(old_node__last_heard__isnull=True) | Q(new_node__last_heard__gte=F("old_node__last_heard"))
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
