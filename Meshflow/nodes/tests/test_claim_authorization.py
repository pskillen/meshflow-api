"""Tests for nodes.claim_authorization."""

from django.test import override_settings

import pytest

from nodes.claim_authorization import normalize_claim_key, try_accept_node_claim
from nodes.models import NodeOwnerClaim
from packets.signals import node_claim_authorized


@pytest.mark.django_db
def test_normalize_claim_key_collapses_whitespace():
    assert normalize_claim_key("  Word   Word   42  ") == "word word 42"


@pytest.mark.django_db
def test_try_accept_node_claim_rejects_non_matching_text(create_observed_node, create_user, create_managed_node):
    user = create_user()
    node = create_observed_node()
    observer = create_managed_node()
    NodeOwnerClaim.objects.create(node=node, user=user, claim_key="word word 99", accepted_at=None)

    captured = []

    def handler(sender, node, claim, observer, **kwargs):
        captured.append((node, claim))

    node_claim_authorized.connect(handler)

    try:
        assert (
            try_accept_node_claim(
                sender=node,
                message_text="not a claim key at all",
                observer=observer,
                sender_service=object(),
            )
            is False
        )
        assert len(captured) == 0
        node.refresh_from_db()
        assert node.claimed_by_id is None
    finally:
        node_claim_authorized.disconnect(handler)


@pytest.mark.django_db
def test_try_accept_node_claim_success(create_observed_node, create_user, create_managed_node):
    user = create_user()
    node = create_observed_node()
    observer = create_managed_node()
    claim = NodeOwnerClaim.objects.create(
        node=node,
        user=user,
        claim_key="word word 123",
        accepted_at=None,
    )

    captured = []

    def handler(sender, node, claim, observer, **kwargs):
        captured.append((sender, node, claim, observer))

    node_claim_authorized.connect(handler)

    try:
        assert (
            try_accept_node_claim(
                sender=node,
                message_text="word word 123",
                observer=observer,
                sender_service=object(),
            )
            is True
        )
        assert len(captured) == 1
        claim.refresh_from_db()
        node.refresh_from_db()
        assert claim.accepted_at is not None
        assert node.claimed_by_id == user.id
    finally:
        node_claim_authorized.disconnect(handler)


@pytest.mark.django_db
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
def test_try_accept_triggers_ws_receiver(create_observed_node, create_user, create_managed_node):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from common.ws_groups import user_claims_ws_group

    user = create_user()
    node = create_observed_node()
    observer = create_managed_node()
    NodeOwnerClaim.objects.create(
        node=node,
        user=user,
        claim_key="alpha beta 55",
        accepted_at=None,
    )

    channel_layer = get_channel_layer()
    group = user_claims_ws_group(user.id)

    async def collect():
        channel = await channel_layer.new_channel()
        await channel_layer.group_add(group, channel)
        return channel

    channel = async_to_sync(collect)()

    try_accept_node_claim(
        sender=node,
        message_text="alpha beta 55",
        observer=observer,
        sender_service=object(),
    )

    msg = async_to_sync(channel_layer.receive)(channel)
    assert msg["type"] == "node_claim_update"
    assert msg["payload"]["event"] == "node_claim_accepted"
    assert msg["payload"]["node_internal_id"] == str(node.internal_id)
