"""inferred_firmware / inferred_firmware_basis on the ObservedNode API."""

from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import RequestFactory

import pytest

from common import meshtastic_firmware as fw
from common.meshtastic_firmware import Verdict
from common.protocol import Protocol
from nodes.serializers import ObservedNodeSerializer
from nodes.services.node_firmware import refresh_inferred_firmware

pytestmark = pytest.mark.django_db


def _data(node):
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    return ObservedNodeSerializer(node, context={"request": request}).data


def test_stored_value_is_returned(create_observed_node):
    node = create_observed_node(inferred_firmware="2.8", inferred_firmware_basis="key_identity")

    data = _data(node)

    assert data["inferred_firmware"] == "2.8"
    assert data["inferred_firmware_basis"] == "key_identity"
    assert "inferred_firmware_at" not in data


def test_no_evidence_is_null_for_both(create_observed_node):
    data = _data(create_observed_node())

    assert data["inferred_firmware"] is None
    assert data["inferred_firmware_basis"] is None


def test_meshcore_is_null_for_both(create_observed_node):
    node = create_observed_node(protocol=Protocol.MESHCORE, meshtastic_node_id=None)
    assert refresh_inferred_firmware(node) is False

    data = _data(node)

    assert data["inferred_firmware"] is None
    assert data["inferred_firmware_basis"] is None


def test_fields_are_read_only():
    meta = ObservedNodeSerializer.Meta
    assert {"inferred_firmware", "inferred_firmware_basis"} <= set(meta.read_only_fields)
    assert "inferred_firmware_at" not in meta.fields


def test_adding_a_generation_needs_no_migration_or_serializer_change(create_observed_node, monkeypatch):
    monkeypatch.setattr(fw, "RULES", [lambda evidence: Verdict("2.9", "test_rule"), *fw.RULES])
    node = create_observed_node()

    assert refresh_inferred_firmware(node) is True
    node.save()
    node.refresh_from_db()

    assert _data(node)["inferred_firmware"] == "2.9"
    assert _data(node)["inferred_firmware_basis"] == "test_rule"
    call_command("makemigrations", "--check", "--dry-run")
