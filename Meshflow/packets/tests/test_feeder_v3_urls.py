"""URL routing for feeder API v3."""

from django.urls import reverse


def test_v3_node_upsert_url_resolves():
    url = reverse(
        "meshtastic-node-upsert-v3",
        kwargs={"node_id": 2997338904},
    )
    assert url == "/api/v3/packets/2997338904/nodes/"
