import pytest

from common import meshtastic_firmware as fw
from common.meshtastic_firmware import (
    BASIS_KEY_IDENTITY,
    BASIS_PREDICTED_ID,
    Evidence,
    Verdict,
    classify,
    generation_for_version,
)


@pytest.mark.parametrize(
    "evidence, expected",
    [
        (Evidence(node_num=5, key_node_id=5), Verdict("2.8", BASIS_KEY_IDENTITY)),
        (Evidence(node_num=5, key_node_id=6), Verdict("2.7", BASIS_KEY_IDENTITY)),
        (Evidence(node_num=5, number_is_another_nodes_key_id=True), Verdict("2.8", BASIS_PREDICTED_ID)),
        (Evidence(node_num=5), None),
        (Evidence(node_num=None), None),
        # A known key outranks the prediction.
        (Evidence(node_num=5, key_node_id=6, number_is_another_nodes_key_id=True), Verdict("2.7", BASIS_KEY_IDENTITY)),
    ],
)
def test_classify_table(evidence, expected):
    assert classify(evidence) == expected


def test_first_verdict_wins(monkeypatch):
    monkeypatch.setattr(fw, "RULES", [lambda e: Verdict("9.9", "first"), lambda e: Verdict("1.1", "second")])
    assert classify(Evidence(node_num=1)) == Verdict("9.9", "first")


def test_none_rule_falls_through(monkeypatch):
    monkeypatch.setattr(fw, "RULES", [lambda e: None, lambda e: Verdict("1.1", "second")])
    assert classify(Evidence(node_num=1)) == Verdict("1.1", "second")


@pytest.mark.parametrize(
    "version, expected",
    [
        ("2.6.11", "2.7"),
        ("2.7.26.54e0d8d", "2.7"),
        ("2.8.2.d5f1619", "2.8"),
        ("v2.8.0", "2.8"),
        ("2.9.1", "2.8"),
        ("3.0.0", "2.8"),
        ("1.2", "2.7"),
        ("garbage", None),
        ("", None),
        (None, None),
        ("2", None),
    ],
)
def test_generation_for_version(version, expected):
    assert generation_for_version(version) == expected


def test_new_floor_adds_generation(monkeypatch):
    monkeypatch.setattr(fw, "GENERATION_FLOORS", [(2, 8), (2, 9)])
    assert generation_for_version("2.9.1") == "2.9"
    assert generation_for_version("2.8.9") == "2.8"
    assert generation_for_version("3.0.0") == "2.9"
