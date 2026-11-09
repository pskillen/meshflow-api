"""How a packet reached the feeder (viaMqtt, transportMechanism) and the hop_limit absent-means-0 rule."""

from datetime import datetime
from types import SimpleNamespace

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.meshtastic_enums import normalise_transport
from nodes.models import NodeLatestStatus, ObservedNode
from nodes.tests.conftest import create_observed_node  # noqa: F401
from packets.hops import (
    NON_RF_TRANSPORTS,
    observation_hop_count,
    observation_is_direct,
    observation_is_rf,
    rf_observations,
    update_inferred_max_hops,
)
from packets.models import MessagePacket, PacketObservation
from packets.serializers import MessagePacketSerializer, PrefetchedPacketObservationSerializer
from packets.tests.test_packet_serializers import BasePacketSerializerTestCase


@pytest.mark.parametrize(
    "value,expected",
    [
        ("TRANSPORT_MQTT", "TRANSPORT_MQTT"),
        (5, "TRANSPORT_MQTT"),
        ("5", "TRANSPORT_MQTT"),
        (1, "TRANSPORT_LORA"),
        (0, "TRANSPORT_INTERNAL"),
        (99, "TRANSPORT_99"),
        (None, None),
        ("", None),
        ("  ", None),
        ("TRANSPORT_" + "X" * 30, None),  # 40 characters: more than the column holds
        ("TRANSPORT_" + "X" * 22, "TRANSPORT_" + "X" * 22),  # exactly 32
        (10**40, None),
        ("9" * 5000, None),
        ("TRANSPORT_\x00MQTT", None),
    ],
)
def test_normalise_transport(value, expected):
    assert normalise_transport(value) == expected


class ObservationTransportSerializerTest(BasePacketSerializerTestCase):
    def _observe(self, packet_id, **extra):
        data = {
            "id": packet_id,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hi"},
            "rxTime": 1672531200,
        }
        data.update(extra)
        serializer = MessagePacketSerializer(data=data, context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.save().observations.get()

    def test_via_mqtt_true(self):
        self.assertIs(self._observe(1, viaMqtt=True).via_mqtt, True)

    def test_via_mqtt_absent_is_false(self):
        self.assertIs(self._observe(2).via_mqtt, False)

    def test_transport_name(self):
        self.assertEqual(self._observe(3, transportMechanism="TRANSPORT_LORA").transport_mechanism, "TRANSPORT_LORA")

    def test_transport_int(self):
        self.assertEqual(self._observe(4, transportMechanism=5).transport_mechanism, "TRANSPORT_MQTT")

    def test_transport_unknown_int(self):
        self.assertEqual(self._observe(5, transportMechanism=42).transport_mechanism, "TRANSPORT_42")

    def test_transport_absent_is_null_not_lora(self):
        self.assertIsNone(self._observe(6).transport_mechanism)

    def test_transport_null_is_null(self):
        self.assertIsNone(self._observe(7, transportMechanism=None).transport_mechanism)

    def test_observation_api_carries_via_mqtt_and_transport(self):
        cases = [
            (20, {"viaMqtt": True, "transportMechanism": "TRANSPORT_MQTT"}, True, "TRANSPORT_MQTT"),
            (21, {"transportMechanism": "TRANSPORT_LORA"}, False, "TRANSPORT_LORA"),
            (22, {}, False, None),  # legacy or own packet: no transport
        ]
        for packet_id, extra, via_mqtt, transport in cases:
            with self.subTest(packet_id=packet_id):
                data = PrefetchedPacketObservationSerializer(self._observe(packet_id, **extra)).data
                self.assertIs(data["via_mqtt"], via_mqtt)
                self.assertEqual(data["transport_mechanism"], transport)

    def test_hop_limit_absent_with_hop_start_is_zero(self):
        observation = self._observe(8, hopStart=3)
        self.assertEqual(observation.hop_limit, 0)
        self.assertEqual(observation_hop_count(observation), 3)

    def test_hop_limit_absent_on_replay_stays_unknown(self):
        observation = self._observe(9, hopStart=3, replayed=True)
        self.assertIsNone(observation.hop_limit)
        self.assertIsNone(observation_hop_count(observation))

    def test_hop_limit_absent_without_hop_start_stays_unknown(self):
        self.assertIsNone(self._observe(10).hop_limit)

    def test_hop_start_zero_stays_unknown(self):
        observation = self._observe(11, hopStart=0)
        self.assertIsNone(observation.hop_limit)
        self.assertIsNone(observation_hop_count(observation))

    def test_hop_limit_present_is_kept(self):
        self.assertEqual(self._observe(12, hopStart=3, hopLimit=2).hop_limit, 2)


def obs(**kwargs):
    base = dict(hop_start=3, hop_limit=3, bitfield=None, replayed=False, via_mqtt=None, transport_mechanism=None)
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("transport", sorted(NON_RF_TRANSPORTS))
def test_non_rf_transport_has_no_hops_and_is_not_direct(transport):
    observation = obs(transport_mechanism=transport)
    assert observation_is_rf(observation) is False
    assert observation_hop_count(observation) is None
    assert observation_is_direct(observation) is False


def test_via_mqtt_has_no_hops_and_is_not_direct():
    observation = obs(via_mqtt=True)
    assert observation_is_rf(observation) is False
    assert observation_hop_count(observation) is None
    assert observation_is_direct(observation) is False


@pytest.mark.parametrize("transport", [None, "TRANSPORT_LORA", "TRANSPORT_LORA_ALT1", "TRANSPORT_INTERNAL"])
def test_null_and_radio_transports_behave_as_before(transport):
    observation = obs(transport_mechanism=transport, via_mqtt=False)
    assert observation_is_rf(observation) is True
    assert observation_hop_count(observation) == 0
    assert observation_is_direct(observation) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kwargs", [{"via_mqtt": True}, *({"transport_mechanism": t} for t in sorted(NON_RF_TRANSPORTS))]
)
def test_non_rf_sets_no_inferred_max_hops(create_observed_node, kwargs):  # noqa: F811
    node = create_observed_node()
    assert update_inferred_max_hops(node, obs(**kwargs), "TEXT_MESSAGE_APP") is False
    assert not NodeLatestStatus.objects.filter(node=node, meshtastic_inferred_max_hops__isnull=False).exists()


@pytest.mark.django_db
def test_null_transport_still_sets_inferred_max_hops(create_observed_node):  # noqa: F811
    node = create_observed_node()
    assert update_inferred_max_hops(node, obs(), "TEXT_MESSAGE_APP") is True


@pytest.mark.django_db
def test_rf_observations_keeps_null_and_radio_and_drops_the_rest(create_packet_observation, create_managed_node):
    observer = create_managed_node()
    rows = {}
    for name, kwargs in {
        "null": {},
        "lora": {"transport_mechanism": "TRANSPORT_LORA", "via_mqtt": False},
        "mqtt": {"transport_mechanism": "TRANSPORT_MQTT", "via_mqtt": True},
        "flag": {"via_mqtt": True},
        "udp": {"transport_mechanism": "TRANSPORT_UNICAST_UDP"},
        "multicast": {"transport_mechanism": "TRANSPORT_MULTICAST_UDP"},
        "api": {"transport_mechanism": "TRANSPORT_API"},
    }.items():
        rows[name] = create_packet_observation(observer=observer, **kwargs).pk
    kept = set(rf_observations(PacketObservation.objects.filter(observer=observer)).values_list("pk", flat=True))
    assert kept == {rows["null"], rows["lora"]}


MANAGED = 111111111
RANGE = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
RX = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))


@pytest.mark.django_db
def test_neighbour_stats_exclude_mqtt_and_udp_and_keep_null_transport(create_managed_node, create_user):
    user = create_user()
    managed = create_managed_node(owner=user, meshtastic_node_id=MANAGED)
    senders = {"null": 201, "lora": 202, "mqtt": 203, "udp": 204}
    transports = {"null": None, "lora": "TRANSPORT_LORA", "mqtt": "TRANSPORT_MQTT", "udp": "TRANSPORT_UNICAST_UDP"}
    for number, (name, sender) in enumerate(senders.items(), start=1):
        ObservedNode.objects.get_or_create(meshtastic_node_id=sender, defaults={"short_name": "N", "long_name": "N"})
        packet = MessagePacket.objects.create(
            packet_id=number, from_int=sender, first_reported_time=RX, message_text="x"
        )
        PacketObservation.objects.create(
            packet=packet,
            observer=managed,
            channel=managed.meshtastic_channel_0,
            rx_time=RX,
            transport_mechanism=transports[name],
            via_mqtt=True if name == "mqtt" else None,
        )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(reverse("stats:node-neighbour-stats", kwargs={"node_id": MANAGED}), RANGE)

    assert response.status_code == 200
    assert sorted(item["source"] for item in response.data["by_source"]) == [senders["null"], senders["lora"]]
