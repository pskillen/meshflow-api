"""Resolve ADVERT fields from flattened ingest bodies or nested companion envelopes."""

from __future__ import annotations

from typing import Any, Iterable


def iter_advert_field_dicts(raw_json: dict) -> Iterable[dict]:
    """Yield dicts to search for adv_* keys: top-level ingest body, then nested companion payload."""
    if not raw_json:
        return
    yield raw_json
    nested = raw_json.get("raw") or {}
    if not isinstance(nested, dict):
        return
    payload = nested.get("payload")
    if isinstance(payload, dict):
        yield payload
    if nested.get("event_type") == "rx_log_data" and isinstance(nested.get("payload"), dict):
        yield nested["payload"]


def get_advert_field(raw_json: dict, key: str) -> Any:
    for d in iter_advert_field_dicts(raw_json):
        if key in d and d[key] is not None:
            return d[key]
    return None
