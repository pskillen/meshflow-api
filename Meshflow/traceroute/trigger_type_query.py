"""Parse ``trigger_type`` list query params (legacy slugs and integer strings)."""

from __future__ import annotations

from .models import TriggerType

# Legacy string values stored before integer migration (meshflow-api#218).
LEGACY_SLUG_TO_INT: dict[str, int] = {
    "user": TriggerType.USER,
    "external": TriggerType.EXTERNAL,
    "auto": TriggerType.MONITORING,
    "monitor": TriggerType.NODE_WATCH,
    "new_node_baseline": TriggerType.NEW_NODE_BASELINE,
}

_VALID_INTS = frozenset(int(c.value) for c in TriggerType)


def parse_trigger_type_filter_tokens(tokens: list[str]) -> list[int] | None:
    """
    Map comma-separated query tokens to integer ``TriggerType`` values.

    Accepts legacy slugs (``auto``, ``user``, ``external``, ``monitor``, ``new_node_baseline``) and
    decimal integer strings ``1``–``6``. Unknown tokens are skipped. Returns
    ``None`` if no valid token remains (caller should not filter).
    """
    out: list[int] = []
    for raw in tokens:
        t = raw.strip()
        if not t:
            continue
        low = t.lower()
        if low in LEGACY_SLUG_TO_INT:
            out.append(LEGACY_SLUG_TO_INT[low])
            continue
        try:
            v = int(t, 10)
        except ValueError:
            continue
        if v in _VALID_INTS:
            out.append(v)
    if not out:
        return None
    seen: set[int] = set()
    ordered: list[int] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered
