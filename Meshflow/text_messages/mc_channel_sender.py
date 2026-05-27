"""Infer MeshCore channel message sender from embedded name prefix."""

from __future__ import annotations

from django.db.models import Q

from common.protocol import Protocol
from nodes.models import ObservedNode

from .map_helpers import observed_node_map_position


def parse_mc_channel_sender_label(message_text: str | None) -> str | None:
    """
    Channel text often prefixes the body as ``{name}: {message}`` (colon + space only).

    Returns the name segment or None when the pattern does not match.
    """
    if not message_text:
        return None
    sep = ": "
    idx = message_text.find(sep)
    if idx <= 0:
        return None
    label = message_text[:idx].strip()
    body = message_text[idx + len(sep) :]
    if not label or not body:
        return None
    return label


def serialize_mc_sender_candidate(node: ObservedNode) -> dict:
    return {
        "internal_id": str(node.internal_id),
        "node_id_str": node.node_id_str,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "position": observed_node_map_position(node),
    }


def mc_sender_candidates_for_label(label: str) -> list[ObservedNode]:
    if not label:
        return []
    return list(
        ObservedNode.objects.filter(protocol=Protocol.MESHCORE)
        .filter(Q(long_name__iexact=label) | Q(short_name__iexact=label))
        .select_related("latest_status")
        .order_by("-last_heard")
    )


def _candidates_for_nodes(nodes: list[ObservedNode]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for node in nodes:
        key = str(node.internal_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(serialize_mc_sender_candidate(node))
    return out


def mc_sender_candidates_for_message(message_text: str | None) -> list[dict]:
    label = parse_mc_channel_sender_label(message_text)
    if not label:
        return []
    return _candidates_for_nodes(mc_sender_candidates_for_label(label))


def bulk_mc_sender_candidates_by_label(labels: set[str]) -> dict[str, list[dict]]:
    if not labels:
        return {}
    label_list = list(labels)
    q = Q()
    for label in label_list:
        q |= Q(long_name__iexact=label) | Q(short_name__iexact=label)
    nodes = ObservedNode.objects.filter(protocol=Protocol.MESHCORE).filter(q).select_related("latest_status")
    by_label: dict[str, list[ObservedNode]] = {label: [] for label in label_list}
    label_lower = {label: label.lower() for label in label_list}
    for node in nodes:
        for label in label_list:
            key = label_lower[label]
            if (node.long_name and node.long_name.lower() == key) or (
                node.short_name and node.short_name.lower() == key
            ):
                by_label[label].append(node)
    return {label: _candidates_for_nodes(by_label[label]) for label in label_list}
