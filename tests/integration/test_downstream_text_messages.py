"""
Integration tests for text message packet downstream effects.

Verifies that ingesting text message packets is accepted and processed.
"""

from .conftest import load_fixture


def test_text_message_packet_ingests_successfully(api_client):
    """Ingesting a text message packet should return 201 (message creation is internal)."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201
