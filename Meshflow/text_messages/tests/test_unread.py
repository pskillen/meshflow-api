"""Server-side unread counts and channel mark-read cursors."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.mesh_node_helpers import MESHTASTIC_BROADCAST_ID
from common.protocol import Protocol
from constellations.models import Constellation, MeshCoreChannelType, MessageChannel
from text_messages.models import MessageChannelReadState, TextMessage
from users.models import User

COUNTS_URL = "message-unread-counts"
MARK_URL = "message-channel-mark-read"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="reader", password="x")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other", password="x")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def constellation(user):
    return Constellation.objects.create(name="C", created_by=user)


@pytest.fixture
def mt_channel(constellation):
    return MessageChannel.objects.create(name="LongFast", constellation=constellation, protocol=Protocol.MESHTASTIC)


@pytest.fixture
def mt_channel2(constellation):
    return MessageChannel.objects.create(name="Other", constellation=constellation, protocol=Protocol.MESHTASTIC)


@pytest.fixture
def mc_channel(constellation):
    return MessageChannel.objects.create(
        name="Public",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_type=MeshCoreChannelType.PUBLIC,
    )


def make_msg(channel, sent_at, text="hi", direct=False):
    if channel.protocol == Protocol.MESHCORE:
        return TextMessage.objects.create(
            protocol=Protocol.MESHCORE, channel=channel, sent_at=sent_at, message_text=text
        )
    return TextMessage.objects.create(
        protocol=Protocol.MESHTASTIC,
        channel=channel,
        sent_at=sent_at,
        message_text=text,
        recipient_meshtastic_node_id=123 if direct else MESHTASTIC_BROADCAST_ID,
    )


def start_cursor(user, channel, at):
    return MessageChannelReadState.objects.create(user=user, channel=channel, last_read_at=at)


def get_counts(client):
    r = client.get(reverse(COUNTS_URL))
    assert r.status_code == 200
    return r.json()


def test_requires_auth(db):
    assert APIClient().get(reverse(COUNTS_URL)).status_code in (401, 403)
    assert APIClient().post(reverse(MARK_URL, args=[1])).status_code in (401, 403)


def test_counts_per_channel_and_protocol(client, user, mt_channel, mt_channel2, mc_channel):
    now = timezone.now()
    for ch in (mt_channel, mt_channel2, mc_channel):
        start_cursor(user, ch, now - timedelta(hours=1))
    for _ in range(3):
        make_msg(mt_channel, now - timedelta(minutes=5))
    make_msg(mt_channel2, now - timedelta(minutes=5))
    make_msg(mc_channel, now - timedelta(minutes=5))
    make_msg(mc_channel, now - timedelta(minutes=4))
    make_msg(mt_channel, now - timedelta(hours=2))  # before the cursor

    data = get_counts(client)
    assert data["meshtastic"] == {"total": 4, "channels": {str(mt_channel.id): 3, str(mt_channel2.id): 1}}
    assert data["meshcore"] == {"total": 2, "channels": {str(mc_channel.id): 2}}


def test_cross_protocol_isolation(client, user, mt_channel, mc_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(hours=1))
    start_cursor(user, mc_channel, now - timedelta(hours=1))
    make_msg(mc_channel, now)
    data = get_counts(client)
    assert data["meshtastic"] == {"total": 0, "channels": {}}
    assert data["meshcore"]["total"] == 1

    TextMessage.objects.all().delete()
    make_msg(mt_channel, now)
    data = get_counts(client)
    assert data["meshtastic"]["total"] == 1
    assert data["meshcore"] == {"total": 0, "channels": {}}


def test_direct_messages_not_counted(client, user, mt_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(hours=1))
    make_msg(mt_channel, now, direct=True)
    assert get_counts(client)["meshtastic"]["total"] == 0


def test_no_cursor_starts_at_now(client, user, mt_channel):
    now = timezone.now()
    make_msg(mt_channel, now - timedelta(days=2))
    assert get_counts(client)["meshtastic"]["total"] == 0
    state = MessageChannelReadState.objects.get(user=user, channel=mt_channel)
    assert state.last_read_at >= now
    make_msg(mt_channel, timezone.now() + timedelta(seconds=5))
    assert get_counts(client)["meshtastic"]["total"] == 1


def test_cursors_are_per_user(client, user, other_user, mt_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(hours=1))
    start_cursor(other_user, mt_channel, now + timedelta(hours=1))
    make_msg(mt_channel, now)
    assert get_counts(client)["meshtastic"]["total"] == 1
    other = APIClient()
    other.force_authenticate(other_user)
    assert get_counts(other)["meshtastic"]["total"] == 0


def test_count_capped_and_windowed(client, user, mt_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(days=30))
    TextMessage.objects.bulk_create(
        [
            TextMessage(
                protocol=Protocol.MESHTASTIC,
                channel=mt_channel,
                sent_at=now - timedelta(minutes=i),
                message_text="x",
                recipient_meshtastic_node_id=MESHTASTIC_BROADCAST_ID,
            )
            for i in range(120)
        ]
    )
    make_msg(mt_channel, now - timedelta(days=8))  # outside window
    assert get_counts(client)["meshtastic"]["channels"][str(mt_channel.id)] == 99

    TextMessage.objects.filter(sent_at__gt=now - timedelta(days=1)).delete()
    make_msg(mt_channel, now - timedelta(days=8))
    assert get_counts(client)["meshtastic"]["total"] == 0


def test_mark_read_clears_only_that_channel(client, user, mt_channel, mt_channel2, mc_channel):
    now = timezone.now()
    for ch in (mt_channel, mt_channel2, mc_channel):
        start_cursor(user, ch, now - timedelta(hours=1))
        make_msg(ch, now - timedelta(minutes=1))
    r = client.post(reverse(MARK_URL, args=[mt_channel.id]))
    assert r.status_code == 200
    assert r.json()["channel_id"] == mt_channel.id
    data = get_counts(client)
    assert data["meshtastic"]["channels"] == {str(mt_channel2.id): 1}
    assert data["meshcore"]["total"] == 1


def test_mark_read_up_to_timestamp_and_message_id(client, user, mt_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(hours=1))
    m1 = make_msg(mt_channel, now - timedelta(minutes=30))
    make_msg(mt_channel, now - timedelta(minutes=20))
    make_msg(mt_channel, now - timedelta(minutes=10))
    url = reverse(MARK_URL, args=[mt_channel.id])

    assert client.post(url, {"up_to": str(m1.id)}, format="json").status_code == 200
    assert get_counts(client)["meshtastic"]["total"] == 2

    ts = (now - timedelta(minutes=15)).isoformat()
    assert client.post(url, {"up_to": ts}, format="json").status_code == 200
    assert get_counts(client)["meshtastic"]["total"] == 1


def test_mark_read_cursor_never_regresses(client, user, mt_channel):
    now = timezone.now()
    start_cursor(user, mt_channel, now - timedelta(hours=1))
    url = reverse(MARK_URL, args=[mt_channel.id])
    client.post(url)
    before = MessageChannelReadState.objects.get(user=user, channel=mt_channel).last_read_at
    older = (now - timedelta(days=1)).isoformat()
    r = client.post(url, {"up_to": older}, format="json")
    assert r.status_code == 200
    assert MessageChannelReadState.objects.get(user=user, channel=mt_channel).last_read_at == before


def test_mark_read_future_up_to_clamped_to_now(client, user, mt_channel):
    url = reverse(MARK_URL, args=[mt_channel.id])
    future = timezone.now() + timedelta(days=5)
    client.post(url, {"up_to": future.isoformat()}, format="json")
    state = MessageChannelReadState.objects.get(user=user, channel=mt_channel)
    assert state.last_read_at <= timezone.now()


def test_mark_read_creates_cursor_when_missing(client, user, mt_channel):
    assert client.post(reverse(MARK_URL, args=[mt_channel.id])).status_code == 200
    assert MessageChannelReadState.objects.filter(user=user, channel=mt_channel).count() == 1


def test_mark_read_bad_up_to(client, mt_channel, mc_channel):
    url = reverse(MARK_URL, args=[mt_channel.id])
    assert client.post(url, {"up_to": "garbage"}, format="json").status_code == 400
    mc_msg = make_msg(mc_channel, timezone.now())
    # message id from another channel is rejected
    assert client.post(url, {"up_to": str(mc_msg.id)}, format="json").status_code == 400


def test_mark_read_unknown_channel_404(client, db):
    assert client.post(reverse(MARK_URL, args=[99999])).status_code == 404


def test_mark_read_hidden_channel_404(client, mt_channel, monkeypatch):
    """Channels outside the visibility scope behave as nonexistent."""
    from constellations.models import MessageChannel as MC
    from text_messages import unread

    monkeypatch.setattr(unread, "visible_channels", lambda: MC.objects.exclude(pk=mt_channel.pk))
    assert client.post(reverse(MARK_URL, args=[mt_channel.id])).status_code == 404
    assert str(mt_channel.id) not in get_counts(client)["meshtastic"]["channels"]


def test_unread_counts_query_count_is_fixed(client, user, constellation, mt_channel):
    now = timezone.now()

    def populate(n):
        for i in range(n):
            ch = MessageChannel.objects.create(
                name=f"mt{i}-{timezone.now().timestamp()}", constellation=constellation, protocol=Protocol.MESHTASTIC
            )
            start_cursor(user, ch, now - timedelta(hours=1))
            make_msg(ch, now)

    populate(2)
    get_counts(client)  # warm: cursor for fixture channel created
    with CaptureQueriesContext(connection) as small:
        get_counts(client)
    populate(8)
    with CaptureQueriesContext(connection) as large:
        get_counts(client)
    assert len(large) == len(small)
    assert len(large) <= 4
