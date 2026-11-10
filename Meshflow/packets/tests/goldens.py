"""Helpers for the Meshtastic 2.7/2.8 capture goldens (``docs/packets/meshtastic-2.8``).

Each golden pairs a wire body (what the bot sends) with what the API stores and does with it. The helpers load the
manifest, post a wire body to the v4 (or v3) ingest URL against a fresh single-feeder setup, snapshot the outcome and
compare it with the committed golden. ``MESHFLOW_REGEN_GOLDENS=1`` writes the golden files instead of comparing.

Volatile values (upload and first-reported times, auto ids, UUIDs, ``last_heard``, ``*_at`` and ``*_reported_time``
stamps) never appear in a
golden. Effects are booleans and counts measured against a snapshot taken before the POST.
"""

from __future__ import annotations

import datetime
import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from django.db import models
from django.urls import reverse

from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import DeviceMetrics, EnvironmentMetrics, NodeAuth, NodeLatestStatus, ObservedNode, Position
from packets.hops import observation_hop_count, observation_is_direct
from packets.models import (
    AirQualityMetricsPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    GenericPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    LocalStatsPacket,
    MessagePacket,
    MtRawPacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    PowerMetricsPacket,
    TraceroutePacket,
    TrafficManagementStatsPacket,
)

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "docs" / "packets" / "meshtastic-2.8"

# The one physical radio (NIAV-1) across an upgrade and a re-key. Prod keeps the number the feeder registered with.
REGISTERED_FEEDER_NUM = 0x1A83CF89

REGEN = bool(os.environ.get("MESHFLOW_REGEN_GOLDENS"))

_PACKET_MODELS = [
    MessagePacket,
    PositionPacket,
    NodeInfoPacket,
    DeviceMetricsPacket,
    LocalStatsPacket,
    EnvironmentMetricsPacket,
    AirQualityMetricsPacket,
    PowerMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    TrafficManagementStatsPacket,
    TraceroutePacket,
    GenericPacket,
]

_PACKET_SKIP = {"id", "first_reported_time"}
_NLS_SKIP = {"id", "node"}


def load_manifest() -> list[dict]:
    return json.loads((GOLDEN_DIR / "manifest.json").read_text(encoding="utf-8"))


def case_ids() -> list[str]:
    """Golden names: every key, plus ``<key>+flag`` for the replay keys."""
    ids = []
    for entry in load_manifest():
        ids.append(entry["key"])
        if entry["kind"] == "replay":
            ids.append(f"{entry['key']}+flag")
    return ids


def entry_for(name: str) -> dict:
    key = name.removesuffix("+flag")
    return next(e for e in load_manifest() if e["key"] == key)


def load_wire(name: str) -> dict:
    return json.loads((GOLDEN_DIR / "wire" / f"{name}.json").read_text(encoding="utf-8"))


def load_golden(name: str) -> dict:
    return json.loads(golden_path(name).read_text(encoding="utf-8"))


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / "golden" / f"{name}.json"


def _jsonable(value):
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _field_values(instance, skip=()) -> dict:
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in skip or field.primary_key or field.name.endswith("_ptr"):
            continue
        if isinstance(field, models.ForeignKey):
            continue
        values[field.name] = _jsonable(getattr(instance, field.attname))
    return values


def setup_feeder(create_managed_node, create_node_api_key):
    """One ManagedNode registered with the pre-upgrade number, on a single-feeder key."""
    node = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=REGISTERED_FEEDER_NUM)
    api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return node, api_key


def post_wire(body: dict, node, api_key, *, url="v4", feeder_num=None):
    client = APIClient()
    if url == "v3":
        return client.post(
            reverse("meshtastic-packet-ingest-v3", kwargs={"node_id": node.meshtastic_node_id}),
            body,
            format="json",
            HTTP_X_API_KEY=api_key.key,
        )
    extra = {"HTTP_X_MESHTASTIC_FEEDER_NODE_NUM": str(feeder_num)} if feeder_num else {}
    return client.post(reverse("feeder-v4-meshtastic-ingest"), body, format="json", HTTP_X_API_KEY=api_key.key, **extra)


@contextmanager
def guarded_side_effects(settings):
    """Patch the DX-detection and new-node-baseline entry points where they are looked up."""
    settings.DX_MONITORING_DETECTION_ENABLED = True
    with (
        patch("dx_monitoring.services.maybe_detect_dx_candidate") as dx,
        patch("packets.receivers.enqueue_new_node_baseline") as baseline_a,
        patch("traceroute.receivers.enqueue_new_node_baseline") as baseline_b,
    ):
        yield {"dx": dx, "baseline_a": baseline_a, "baseline_b": baseline_b}


class Snapshot:
    """State of the sender's rows before a POST, to measure effects against."""

    def __init__(self, sender: int):
        self.sender = sender
        node = ObservedNode.objects.filter(meshtastic_node_id=sender).first()
        self.node_existed = node is not None
        self.last_heard = node.last_heard if node else None
        status = NodeLatestStatus.objects.filter(node=node).first() if node else None
        self.nls = _field_values(status, _NLS_SKIP) if status else {}


def _concrete_packet(raw: MtRawPacket):
    for model in _PACKET_MODELS:
        row = model.objects.filter(pk=raw.pk).first()
        if row is not None:
            return row
    return raw


def _channel_index(observation: PacketObservation):
    if observation.channel_id is None:
        return None
    for idx in range(8):
        if getattr(observation.observer, f"meshtastic_channel_{idx}_id") == observation.channel_id:
            return idx
    return "unmapped"


def observation_snapshot(observation: PacketObservation) -> dict:
    return {
        "hop_start": observation.hop_start,
        "hop_limit": observation.hop_limit,
        "bitfield": observation.bitfield,
        "rx_rssi": observation.rx_rssi,
        "rx_snr": observation.rx_snr,
        "rx_time": _jsonable(observation.rx_time),
        "rx_time_estimated": observation.rx_time_estimated,
        "relay_node": observation.relay_node,
        "via_mqtt": observation.via_mqtt,
        "transport_mechanism": observation.transport_mechanism,
        "xeddsa_signed": observation.xeddsa_signed,
        "ack_proof_status": observation.ack_proof_status,
        "replayed": observation.replayed,
        "channel": _channel_index(observation),
    }


def _nls_changes(snapshot: Snapshot) -> dict:
    node = ObservedNode.objects.filter(meshtastic_node_id=snapshot.sender).first()
    status = NodeLatestStatus.objects.filter(node=node).first() if node else None
    if status is None:
        return {}
    after = _field_values(status, _NLS_SKIP)
    return {
        name: value
        for name, value in after.items()
        if value is not None
        and value != snapshot.nls.get(name)
        and not name.endswith(("_at", "_reported_time"))  # stamped from the API clock
    }


def _observed_node_snapshot(sender: int):
    node = ObservedNode.objects.filter(meshtastic_node_id=sender).first()
    if node is None:
        return None
    return {
        name: value
        for name, value in _field_values(node).items()
        if not isinstance(ObservedNode._meta.get_field(name), models.DateTimeField)
    }


def outcome(response, request: dict, snapshot: Snapshot, side_effects: dict) -> dict:
    """The golden for one POST: status, stored packet, observation and effects."""
    result = {"request": request, "status": response.status_code}
    raw = MtRawPacket.objects.first()
    if raw is None:
        result.update(packet=None, observation=None, observed_node=None, effects={"rows": 0})
        return result

    packet = _concrete_packet(raw)
    observation = PacketObservation.objects.select_related("observer").get(packet=raw)
    node = ObservedNode.objects.filter(meshtastic_node_id=snapshot.sender).first()
    nls = _nls_changes(snapshot)
    result["packet"] = {"model": type(packet).__name__, "fields": _field_values(packet, _PACKET_SKIP)}
    result["observation"] = observation_snapshot(observation)
    result["observed_node"] = _observed_node_snapshot(snapshot.sender)
    result["effects"] = {
        "observed_node_created": node is not None and not snapshot.node_existed,
        "last_heard_advanced": node is not None
        and node.last_heard is not None
        and (snapshot.last_heard is None or node.last_heard > snapshot.last_heard),
        "position_rows": Position.objects.count(),
        "device_metrics_rows": DeviceMetrics.objects.count(),
        "environment_metrics_rows": EnvironmentMetrics.objects.count(),
        "nls": nls,
        "inferred_max_hops": nls.get("meshtastic_inferred_max_hops"),
        "dx_candidate_called": side_effects["dx"].called,
        "baseline_traceroute_queued": side_effects["baseline_a"].called or side_effects["baseline_b"].called,
        "observation_api": {
            "replayed": observation.replayed,
            "hop_count": observation_hop_count(observation),
            "direct_from_sender": observation_is_direct(observation),
        },
    }
    return result


def run_case(name: str, node, api_key, side_effects: dict, *, url="v4", body: dict | None = None) -> dict:
    """POST one case (the stored wire body unless ``body`` is given) and return its outcome."""
    entry = entry_for(name)
    body = load_wire(name) if body is None else body
    snapshot = Snapshot(body["from"])
    response = post_wire(body, node, api_key, url=url, feeder_num=entry["feeder_num"])
    request = {"url": url, "feeder_num_header": entry["feeder_num"] if url == "v4" else None}
    return outcome(response, request, snapshot, side_effects)


def assert_golden(name: str, actual: dict) -> None:
    """Assert ``actual`` equals ``golden/<name>.json``."""
    expected = json.loads(golden_path(name).read_text(encoding="utf-8"))
    # Round trip so tuples and non-JSON types compare like the file does.
    assert json.loads(json.dumps({"key": name, **actual}, sort_keys=True)) == expected


def check_golden(name: str, actual: dict) -> None:
    """Compare ``actual`` with ``golden/<name>.json``; write it instead when regenerating."""
    if REGEN:
        path = golden_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key": name, **actual}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    assert_golden(name, actual)
