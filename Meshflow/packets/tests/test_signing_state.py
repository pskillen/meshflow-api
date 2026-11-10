"""XEdDSA signing state: stored per observation, per raw packet and per sender; read-only in the API.

Unsigned is the normal state on 2.8 (the default policy does not sign) and absent means unknown: None is never
coerced to False.
"""

from datetime import timedelta

from django.utils import timezone

import pytest

from common.meshtastic_enums import normalise_ack_proof
from nodes.models import ManagedNode, ObservedNode
from nodes.serializers import ObservedNodeSerializer
from packets.models import MtRawPacket, PacketObservation
from packets.serializers import MessagePacketSerializer, PrefetchedPacketObservationSerializer
from packets.services.text_message import TextMessagePacketService
from packets.tests import goldens
from packets.tests.test_packet_serializers import BasePacketSerializerTestCase

SIGNATURE = "6O2jR/JZB9f0jFswDTZWazoyTa0b890c60YiWNboocHLdmjciFPz9h/OydjhuV2eMXPVAyHG+ueHIsJ38fV5AQ=="


class SigningIngestTest(BasePacketSerializerTestCase):
    def _other_observer(self):
        return ManagedNode.objects.create(
            meshtastic_node_id=123456790,
            name="Other",
            constellation_id=self.constellation.id,
            owner=self.user,
        )

    def _observe(self, packet_id=1, observer=None, decoded_extra=None, **extra):
        decoded = {"portnum": "TEXT_MESSAGE_APP", "text": "hi"}
        decoded.update(decoded_extra or {})
        data = {
            "id": packet_id,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": decoded,
            "rxTime": int(timezone.now().timestamp()),
            "hopStart": 3,
            "hopLimit": 3,
        }
        data.update(extra)
        context = {"observer": observer or self.observer}
        serializer = MessagePacketSerializer(data=data, context=context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        packet = serializer.save()
        return packet, serializer.observation

    def test_absent_is_null_not_false(self):
        packet, observation = self._observe()
        self.assertIsNone(observation.xeddsa_signed)
        self.assertIsNone(observation.ack_proof_status)
        self.assertIsNone(packet.xeddsa_signature_present)

    def test_false_stays_false(self):
        _, observation = self._observe(xeddsaSigned=False)
        self.assertIs(observation.xeddsa_signed, False)

    def test_true_stays_true(self):
        _, observation = self._observe(xeddsaSigned=True)
        self.assertIs(observation.xeddsa_signed, True)

    def test_explicit_null_and_junk_are_unknown(self):
        for index, value in enumerate([None, "true", 1, 0, "", []]):
            _, observation = self._observe(packet_id=10 + index, xeddsaSigned=value)
            self.assertIsNone(observation.xeddsa_signed, value)

    def test_ack_proof_stored_as_the_name(self):
        _, observation = self._observe(ackProofStatus="ACK_PROOF_VALID")
        self.assertEqual(observation.ack_proof_status, "ACK_PROOF_VALID")

    def test_ack_proof_junk_is_null(self):
        for index, value in enumerate([None, "", 1, True, "X" * 40]):
            _, observation = self._observe(packet_id=20 + index, ackProofStatus=value)
            self.assertIsNone(observation.ack_proof_status, value)

    def test_signature_marks_the_raw_packet(self):
        packet, _ = self._observe(xeddsaSigned=True, decoded_extra={"xeddsaSignature": SIGNATURE})
        packet.refresh_from_db()
        self.assertIs(packet.xeddsa_signature_present, True)

    def test_blank_signature_does_not_mark(self):
        packet, _ = self._observe(decoded_extra={"xeddsaSignature": "  "})
        self.assertIsNone(packet.xeddsa_signature_present)

    def test_second_observer_without_signature_does_not_clear(self):
        packet, _ = self._observe(xeddsaSigned=True, decoded_extra={"xeddsaSignature": SIGNATURE})
        _, second = self._observe(observer=self._other_observer())
        self.assertIsNone(second.xeddsa_signed)
        self.assertEqual(MtRawPacket.objects.count(), 1)
        packet.refresh_from_db()
        self.assertIs(packet.xeddsa_signature_present, True)

    def test_second_observer_with_signature_marks_an_unmarked_packet(self):
        packet, _ = self._observe()
        self._observe(observer=self._other_observer(), decoded_extra={"xeddsaSignature": SIGNATURE})
        packet.refresh_from_db()
        self.assertIs(packet.xeddsa_signature_present, True)

    def test_repeat_from_same_observer_writes_nothing_new(self):
        _, first = self._observe(xeddsaSigned=False)
        _, again = self._observe(xeddsaSigned=True, ackProofStatus="ACK_PROOF_INVALID")
        self.assertEqual(again.pk, first.pk)
        again.refresh_from_db()
        self.assertIs(again.xeddsa_signed, False)
        self.assertIsNone(again.ack_proof_status)

    def test_a_27_shaped_packet_is_unchanged_otherwise(self):
        _, observation = self._observe()
        self.assertEqual((observation.hop_start, observation.hop_limit), (3, 3))
        self.assertIs(observation.replayed, False)
        self.assertIs(observation.via_mqtt, False)
        self.assertIsNone(observation.bitfield)
        self.assertIsNone(observation.xeddsa_signed)

    def test_observation_api_exposes_the_fields(self):
        _, observation = self._observe(xeddsaSigned=False, ackProofStatus="ACK_PROOF_NO_KEY")
        data = PrefetchedPacketObservationSerializer(
            PacketObservation.objects.get(pk=observation.pk), context={"observer_nodes_map": {}}
        ).data
        self.assertIs(data["xeddsa_signed"], False)
        self.assertEqual(data["ack_proof_status"], "ACK_PROOF_NO_KEY")


def test_normalise_ack_proof():
    assert normalise_ack_proof("ACK_PROOF_VALID") == "ACK_PROOF_VALID"
    assert normalise_ack_proof(" ACK_PROOF_NO_KEY ") == "ACK_PROOF_NO_KEY"
    assert normalise_ack_proof(None) is None
    assert normalise_ack_proof(2) is None


# --- last signed ---------------------------------------------------------------------------------------------------


def _process(
    create_managed_node,
    create_message_packet,
    create_packet_observation,
    create_user,
    *,
    signed=None,
    first=None,
    replayed=False,
    before=None,
):
    packet = create_message_packet()
    if first is not None:
        packet.first_reported_time = first
        packet.save()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    observation.xeddsa_signed = signed
    observation.replayed = replayed
    observation.save()
    node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    node.meshtastic_last_signed_at = before
    node.save()
    TextMessagePacketService().process_packet(packet, observer, observation, create_user())
    node.refresh_from_db()
    return node


@pytest.mark.django_db
@pytest.mark.parametrize("signed", [None, False])
def test_unsigned_and_unknown_leave_last_signed_alone(
    signed, create_managed_node, create_message_packet, create_packet_observation, create_user
):
    node = _process(
        create_managed_node, create_message_packet, create_packet_observation, create_user, signed=signed
    )
    assert node.meshtastic_last_signed_at is None
    assert node.meshtastic_known_signer is False


@pytest.mark.django_db
def test_signed_sets_last_signed(create_managed_node, create_message_packet, create_packet_observation, create_user):
    first = timezone.now() - timedelta(minutes=5)
    node = _process(
        create_managed_node, create_message_packet, create_packet_observation, create_user, signed=True, first=first
    )
    assert node.meshtastic_last_signed_at == first
    assert node.meshtastic_known_signer is True


@pytest.mark.django_db
def test_signed_moves_forward_only(create_managed_node, create_message_packet, create_packet_observation, create_user):
    now = timezone.now()
    newer = now - timedelta(minutes=1)
    node = _process(
        create_managed_node,
        create_message_packet,
        create_packet_observation,
        create_user,
        signed=True,
        first=now - timedelta(hours=2),
        before=newer,
    )
    assert node.meshtastic_last_signed_at == newer


@pytest.mark.django_db
def test_signed_advances_an_older_value(
    create_managed_node, create_message_packet, create_packet_observation, create_user
):
    now = timezone.now()
    first = now - timedelta(minutes=1)
    node = _process(
        create_managed_node,
        create_message_packet,
        create_packet_observation,
        create_user,
        signed=True,
        first=first,
        before=now - timedelta(days=1),
    )
    assert node.meshtastic_last_signed_at == first


@pytest.mark.django_db
def test_replayed_signed_leaves_last_signed_alone(
    create_managed_node, create_message_packet, create_packet_observation, create_user
):
    node = _process(
        create_managed_node,
        create_message_packet,
        create_packet_observation,
        create_user,
        signed=True,
        replayed=True,
    )
    assert node.meshtastic_last_signed_at is None


# --- node properties -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key_node_id,node_id,expected",
    [(1234, 1234, True), (1234, 5678, False), (None, 5678, None)],
)
def test_v28_identity_property(key_node_id, node_id, expected):
    node = ObservedNode(meshtastic_node_id=node_id, meshtastic_key_node_id=key_node_id)
    assert node.meshtastic_v28_identity is expected


def test_known_signer_property():
    assert ObservedNode().meshtastic_known_signer is False
    assert ObservedNode(meshtastic_last_signed_at=timezone.now()).meshtastic_known_signer is True


@pytest.mark.django_db
def test_observed_node_detail_exposes_both_properties():
    node = ObservedNode.objects.create(
        meshtastic_node_id=777, meshtastic_key_node_id=777, meshtastic_last_signed_at=timezone.now()
    )
    data = ObservedNodeSerializer(node, context={}).data
    assert data["meshtastic_v28_identity"] is True
    assert data["meshtastic_known_signer"] is True
    other = ObservedNode.objects.create(meshtastic_node_id=778)
    data = ObservedNodeSerializer(other, context={}).data
    assert data["meshtastic_v28_identity"] is None
    assert data["meshtastic_known_signer"] is False


# --- end to end ----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_signed_wire_body_end_to_end(feeder, side_effects):
    node, api_key = feeder
    entry = goldens.entry_for("p28s-L16")
    body = goldens.load_wire("p28s-L16")
    assert body["xeddsaSigned"] is True

    response = goldens.post_wire(body, node, api_key, feeder_num=entry["feeder_num"])

    assert response.status_code == 201
    raw = MtRawPacket.objects.get()
    assert raw.xeddsa_signature_present is True
    observation = PacketObservation.objects.get()
    assert observation.xeddsa_signed is True
    assert observation.ack_proof_status is None
    sender = ObservedNode.objects.get(meshtastic_node_id=body["from"])
    assert sender.meshtastic_known_signer is True
