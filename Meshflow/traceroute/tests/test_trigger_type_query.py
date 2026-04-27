"""Tests for trigger_type query parsing (legacy slugs + integers)."""

import pytest

from traceroute.models import AutoTraceRoute, TriggerType
from traceroute.trigger_type_query import LEGACY_SLUG_TO_INT, parse_trigger_type_filter_tokens


def test_legacy_slug_mapping_matches_migration():
    assert LEGACY_SLUG_TO_INT["user"] == TriggerType.USER
    assert LEGACY_SLUG_TO_INT["external"] == TriggerType.EXTERNAL
    assert LEGACY_SLUG_TO_INT["auto"] == TriggerType.MONITORING
    assert LEGACY_SLUG_TO_INT["monitor"] == TriggerType.NODE_WATCH
    assert LEGACY_SLUG_TO_INT["new_node_baseline"] == TriggerType.NEW_NODE_BASELINE


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["user", "1"], [1]),
        (["auto", "3"], [3]),
        (["monitor", "4"], [4]),
        (["new_node_baseline", "6"], [6]),
        (["1", "4", "1"], [1, 4]),
        (["bogus", "99"], None),
        ([], None),
    ],
)
def test_parse_trigger_type_filter_tokens(tokens, expected):
    assert parse_trigger_type_filter_tokens(tokens) == expected


def test_autotraceroute_constants_match_trigger_type():
    assert AutoTraceRoute.TRIGGER_TYPE_USER == TriggerType.USER
    assert AutoTraceRoute.TRIGGER_TYPE_EXTERNAL == TriggerType.EXTERNAL
    assert AutoTraceRoute.TRIGGER_TYPE_MONITORING == TriggerType.MONITORING
    assert AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH == TriggerType.NODE_WATCH
    assert AutoTraceRoute.TRIGGER_TYPE_DX_WATCH == TriggerType.DX_WATCH
    assert AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE == TriggerType.NEW_NODE_BASELINE
