"""Bot -> API contract: the bot's capture subset, through the bot's own serialiser, into this API's ingest.

Needs a meshflow-bot checkout: ``MESHFLOW_BOT_PATH=<checkout> pytest -m contract packets/tests/contract``. Without the
variable the module is skipped. The bot's serialiser, replay classifier and fixture loader are standard library only,
so no bot dependency is installed. See ``tests/TESTING.md`` ("Bot contract test").
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BOT_PATH = os.environ.get("MESHFLOW_BOT_PATH")
if not _BOT_PATH:
    pytest.skip("MESHFLOW_BOT_PATH is not set (path to a meshflow-bot checkout)", allow_module_level=True)

_BOT_ROOT = Path(_BOT_PATH).resolve()
if not (_BOT_ROOT / "docs" / "meshtastic_packets" / "2.8" / "subset.json").is_file():
    pytest.fail(f"MESHFLOW_BOT_PATH={_BOT_ROOT} has no docs/meshtastic_packets/2.8/subset.json", pytrace=False)

for _pkg in ("src", "tools"):
    if importlib.util.find_spec(_pkg) is not None:
        pytest.fail(
            f"the API now has a top-level '{_pkg}' package, which clashes with the bot's; "
            "rework how test_bot_contract.py imports the bot",
            pytrace=False,
        )
sys.path.insert(0, str(_BOT_ROOT))

from django.urls import reverse  # noqa: E402

from rest_framework.test import APIClient  # noqa: E402

try:
    from src.meshtastic.replay import is_replayed  # noqa: E402
    from src.meshtastic.serializers import MeshtasticPacketSerializer  # noqa: E402
    from src.meshtastic.translation import node_dict_to_mesh_node  # noqa: E402
    from tools.meshtastic_fixtures.load import lib_packet, load_subset  # noqa: E402
except ImportError as exc:
    pytest.fail(
        f"bot API changed: {exc}. The bot moved or renamed something this test imports; "
        "update the imports in test_bot_contract.py (and the pin notes in tests/TESTING.md)",
        pytrace=False,
    )

from nodes.models import ObservedNode  # noqa: E402
from packets.tests import goldens  # noqa: E402

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

BOT_PACKETS = _BOT_ROOT / "docs" / "meshtastic_packets" / "2.8"
SUBSET = {entry["key"]: entry for entry in load_subset(BOT_PACKETS)}
API_KEYS = [entry["key"] for entry in goldens.load_manifest()]

BUMP = "update the api goldens and bump .github/contract/bot-ref"


def bot_body(entry: dict, *, flag: bool = False) -> dict:
    """What the bot sends for this capture: its serialiser, with the host clock fixed to the capture time."""
    with patch("src.meshtastic.serializers.time.time", return_value=entry["t_host"]):
        body = MeshtasticPacketSerializer().serialise_raw_packet(lib_packet(entry))
    return {**body, "replayed": True} if flag else body


def _dump(value) -> list[str]:
    return json.dumps(value, indent=2, sort_keys=True).splitlines()


def _diff(name: str, expected: dict, actual: dict) -> str:
    return "\n".join(
        difflib.unified_diff(_dump(expected), _dump(actual), f"wire/{name}.json", "bot output", lineterm="")
    )


def _subset_entry(key: str) -> dict:
    if key not in SUBSET:
        pytest.fail(f"{key} is in the api manifest but not in the bot's subset.json")
    return SUBSET[key]


def test_every_api_key_is_in_the_bot_subset():
    missing = [key for key in API_KEYS if key not in SUBSET]
    assert not missing, f"api manifest keys missing from the bot's subset.json: {missing}"


def test_every_bot_key_has_an_api_golden():
    new = sorted(set(SUBSET) - set(API_KEYS))
    assert not new, f"new bot fixture: add a golden for {new} (api manifest, wire/ and golden/), then bump the pin"


@pytest.mark.parametrize("name", goldens.case_ids())
def test_bot_output_matches_the_wire_body(name):
    actual = bot_body(_subset_entry(name.removesuffix("+flag")), flag=name.endswith("+flag"))
    expected = goldens.load_wire(name)
    assert actual == expected, f"bot output changed: {BUMP}\n{_diff(name, expected, actual)}"


@pytest.mark.parametrize("key", API_KEYS)
def test_replay_classifier_agrees_with_the_api(key):
    entry = _subset_entry(key)
    bot_says = is_replayed(lib_packet(entry), entry["feeder_num"])
    observation = goldens.load_golden(key)["observation"]
    api_says = bool(observation and observation["replayed"])
    assert bot_says == api_says, f"{key}: bot is_replayed={bot_says} but the api golden has replayed={api_says}"


@pytest.mark.parametrize("name", goldens.case_ids())
def test_bot_body_ingests_to_the_golden(name, feeder, side_effects):
    body = bot_body(_subset_entry(name.removesuffix("+flag")), flag=name.endswith("+flag"))
    actual = goldens.run_case(name, *feeder, side_effects, body=body)
    goldens.assert_golden(name, actual)


# --- NodeDB upload ---------------------------------------------------------------------------------------------

ZERO_MAC = "AAAAAAAA"  # base64 of six zero bytes
FULL_MAC = "02:11:22:33:44:55"
NODEDB_CAPTURE = "x28"  # the bot's short id (captures.json) for the 2.8 feeder capture whose NodeDB we replay
NODEDB_CASES = [f"nodedb-{i}" for i in range(5)]


def _user(item: tuple[str, dict]) -> dict:
    return item[1].get("user", {})


def _nodedb_path() -> Path:
    """The x28 capture's nodedb.json, found through the bot's captures.json rather than a directory name."""
    index = BOT_PACKETS / "captures.json"
    if not index.is_file():
        pytest.fail(f"bot layout changed: {index} is missing; update NODEDB_CAPTURE lookup in test_bot_contract.py")
    entries = [e for e in json.loads(index.read_text(encoding="utf-8")) if e.get("short") == NODEDB_CAPTURE]
    if not entries:
        pytest.fail(f"bot captures.json has no capture with short={NODEDB_CAPTURE!r}; update NODEDB_CAPTURE")
    path = BOT_PACKETS / entries[0]["path"] / "nodedb.json"
    if not path.is_file():
        pytest.fail(f"bot capture {NODEDB_CAPTURE!r} has no nodedb.json at {path}; update test_bot_contract.py")
    return path


def _nodedb_sample() -> list[tuple[str, dict]]:
    """Five x28 NodeDB entries: two zeroed MACs, one 24-byte-cut long name, two ordinary."""
    nodes = sorted(json.loads(_nodedb_path().read_text(encoding="utf-8")).items())
    zeroed = [item for item in nodes if _user(item).get("macaddr") == ZERO_MAC]
    cut = [item for item in nodes if len(_user(item).get("longName", "").encode()) == 24]
    chosen = zeroed[:2] + cut[:1]
    ordinary = [item for item in nodes if item not in chosen and _user(item).get("macaddr") not in (None, "", ZERO_MAC)]
    sample = chosen + ordinary[:2]
    n_zeroed = sum(_user(item).get("macaddr") == ZERO_MAC for item in sample)
    n_cut = sum(len(_user(item).get("longName", "").encode()) == 24 for item in sample)
    assert len(sample) == 5 and n_zeroed >= 2 and n_cut >= 1, (
        f"the bot's x28 nodedb.json no longer yields the NodeDB sample (5 entries, >=2 zeroed MACs, >=1 24-byte name): "
        f"got {len(sample)} entries, {n_zeroed} zeroed, {n_cut} cut; pick new entries in _nodedb_sample"
    )
    return sample


@pytest.fixture(scope="module")
def nodedb_sample():
    return _nodedb_sample()


@pytest.mark.parametrize("case", NODEDB_CASES)
def test_nodedb_upload_does_not_clobber_stored_identity(case, nodedb_sample, feeder):
    node, api_key = feeder
    node_id, raw = nodedb_sample[NODEDB_CASES.index(case)]
    user = raw["user"]
    body = MeshtasticPacketSerializer().serialise_node(node_dict_to_mesh_node(raw))

    zeroed = user["macaddr"] == ZERO_MAC
    cut = len(user["longName"].encode()) == 24
    stored_mac = FULL_MAC if zeroed else "02:aa:bb:cc:dd:ee"
    stored_name = f"{body['user']['long_name']} (full name)" if cut else body["user"]["long_name"]
    observed = ObservedNode.objects.create(
        meshtastic_node_id=raw["num"],
        mac_addr=stored_mac,
        long_name=stored_name,
        short_name=user["shortName"][:5],
    )

    response = APIClient().post(
        reverse("feeder-v4-meshtastic-nodes"),
        body,
        format="json",
        HTTP_X_API_KEY=api_key.key,
        HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(goldens.REGISTERED_FEEDER_NUM),
    )

    assert 200 <= response.status_code < 300, response.content
    observed.refresh_from_db()
    assert observed.mac_addr == (FULL_MAC if zeroed else user["macaddr"]), f"{node_id}: MAC was overwritten"
    assert observed.long_name == stored_name, f"{node_id}: long name was overwritten"
