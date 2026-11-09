"""Infer a Meshtastic node's firmware generation from evidence we already hold.

Pure (no ORM): the ORM side lives in ``nodes/services/node_firmware.py``.

Meshtastic 2.8 sets ``node number = crc32(public key)``. A node that holds a key whose crc32 is its number is on
2.8 or later; a node whose number differs from its key's crc32 has not taken the derived number, so it is on 2.7
or earlier. A *missing* key is not evidence of any version, so no rule fires on one.

A generation is a floor, not an exact version: ``"2.8"`` means a 2.8 identity was seen, ``"2.7"`` means 2.7 or
earlier. Adding a future breaking version is one rule in ``RULES`` and one entry in ``GENERATION_FLOORS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

BASIS_FEEDER_REPORT = "feeder_report"
BASIS_KEY_IDENTITY = "key_identity"
BASIS_PREDICTED_ID = "predicted_id"

# The one definition of "active" for adoption statistics.
ADOPTION_WINDOW_HOURS = 168

# (major, minor) at which each generation starts, ascending.
GENERATION_FLOORS: list[tuple[int, int]] = [(2, 8)]
LOWEST_GENERATION = "2.7"  # below the first floor; means "2.7 or earlier"
KEY_DERIVED_ID_GENERATION = "2.8"

_VERSION = re.compile(r"^v?(\d+)\.(\d+)")


@dataclass(frozen=True)
class Evidence:
    node_num: int | None
    key_node_id: int | None = None
    number_is_another_nodes_key_id: bool = False
    feeder_firmware: str | None = None  # version string the node itself reported, when it is one of our feeders


@dataclass(frozen=True)
class Verdict:
    generation: str
    basis: str


def feeder_report_rule(evidence: Evidence) -> Verdict | None:
    """A feeder's own reported version. The only evidence that can show a downgrade."""
    generation = generation_for_version(evidence.feeder_firmware)
    if generation is None:
        return None
    return Verdict(generation, BASIS_FEEDER_REPORT)


def key_identity_rule(evidence: Evidence) -> Verdict | None:
    """A known key either derives the node number (2.8) or does not (2.7 or earlier)."""
    if evidence.key_node_id is None:
        return None
    if evidence.key_node_id == evidence.node_num:
        return Verdict(KEY_DERIVED_ID_GENERATION, BASIS_KEY_IDENTITY)
    return Verdict(LOWEST_GENERATION, BASIS_KEY_IDENTITY)


def predicted_id_rule(evidence: Evidence) -> Verdict | None:
    """A keyless row whose number is another row's key-derived id is that node after taking the 2.8 identity."""
    if evidence.key_node_id is not None:
        return None
    if evidence.number_is_another_nodes_key_id:
        return Verdict(KEY_DERIVED_ID_GENERATION, BASIS_PREDICTED_ID)
    return None


# First non-None verdict wins. Prepend stronger evidence.
RULES: list[Callable[[Evidence], Verdict | None]] = [feeder_report_rule, key_identity_rule, predicted_id_rule]


def classify(evidence: Evidence) -> Verdict | None:
    """The first rule's verdict, or None when there is no evidence. Reads ``RULES`` at call time."""
    for rule in RULES:
        verdict = rule(evidence)
        if verdict is not None:
            return verdict
    return None


def generation_for_version(version: str | None) -> str | None:
    """Map a firmware version string to its generation (``"2.8.2.d5f1619"`` -> ``"2.8"``), or None if unparseable."""
    if not version or not isinstance(version, str):
        return None
    match = _VERSION.match(version.strip())
    if not match:
        return None
    parsed = (int(match.group(1)), int(match.group(2)))
    eligible = [floor for floor in GENERATION_FLOORS if floor <= parsed]
    if not eligible:
        return LOWEST_GENERATION
    major, minor = max(eligible)
    return f"{major}.{minor}"
