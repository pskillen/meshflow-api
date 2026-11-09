"""Learned per-node offline threshold (#455)."""

from datetime import timedelta

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.learned_thresholds import learned_threshold_seconds, node_gaps
from mesh_monitoring.models import NodePresence
from mesh_monitoring.tasks import update_learned_offline_thresholds
from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold

H = 3600


def test_fewer_than_five_gaps_is_none():
    assert learned_threshold_seconds([8 * H] * 4) is None
    assert learned_threshold_seconds([]) is None


def test_lower_bound_is_six_hours():
    assert learned_threshold_seconds([60.0] * 5) == 6 * H


def test_upper_bound_is_forty_eight_hours():
    assert learned_threshold_seconds([30 * H] * 5) == 48 * H


def test_worked_p90():
    # p90 of 10 gaps: position 0.9 * 9 = 8.1 -> 9 h + 0.1 * (12 h - 9 h) = 9.3 h; x3 = 27.9 h.
    gaps = [h * H for h in (3, 3, 3, 3, 3, 3, 3, 3, 9, 12)]
    assert learned_threshold_seconds(gaps) == round(27.9 * H)


@pytest.fixture
def make_packets(create_raw_packet, create_packet_observation, create_managed_node):
    observer = create_managed_node()

    def make(node_id, times, replayed=False):
        out = []
        for i, t in enumerate(times):
            pkt = create_raw_packet(from_int=node_id, packet_id=900000 + i + int(t.timestamp()) % 100000)
            pkt.first_reported_time = t
            pkt.save()
            create_packet_observation(packet=pkt, observer=observer, replayed=replayed)
            out.append(pkt)
        return out

    return make


@pytest.mark.django_db
def test_node_gaps_excludes_replayed_only_packets(create_observed_node, make_packets):
    obs = create_observed_node(meshtastic_node_id=700001)
    now = timezone.now()
    make_packets(700001, [now - timedelta(hours=30), now - timedelta(hours=20), now - timedelta(hours=10)])
    make_packets(700001, [now - timedelta(hours=15)], replayed=True)
    assert node_gaps(obs, now) == [10 * H, 10 * H]


@pytest.mark.django_db
def test_node_gaps_limited_to_seven_days(create_observed_node, make_packets):
    obs = create_observed_node(meshtastic_node_id=700002)
    now = timezone.now()
    make_packets(
        700002, [now - timedelta(days=9), now - timedelta(days=8), now - timedelta(days=2), now - timedelta(days=1)]
    )
    assert node_gaps(obs, now) == [1 * 24 * H]


@pytest.mark.django_db
def test_node_gaps_ignores_other_nodes(create_observed_node, make_packets):
    obs = create_observed_node(meshtastic_node_id=700003)
    now = timezone.now()
    make_packets(700003, [now - timedelta(hours=5), now - timedelta(hours=1)])
    make_packets(799999, [now - timedelta(hours=3)])
    assert node_gaps(obs, now) == [4 * H]


@pytest.mark.django_db
def test_task_updates_only_watched_nodes_and_clears_when_history_disappears(
    create_user, create_observed_node, make_packets
):
    user = create_user()
    watched = create_observed_node(meshtastic_node_id=700010, claimed_by=user)
    unwatched = create_observed_node(meshtastic_node_id=700011)
    now = timezone.now()
    times = [now - timedelta(hours=8 * i) for i in range(1, 12)]
    make_packets(700010, times)
    make_packets(700011, times)
    create_watch_with_offline_threshold(user=user, observed_node=watched, offline_after=21600)

    result = update_learned_offline_thresholds()

    assert result["updated"] == 1
    presence = NodePresence.objects.get(observed_node=watched)
    assert presence.learned_offline_after_seconds == 24 * H
    assert presence.learned_offline_computed_at is not None
    assert not NodePresence.objects.filter(observed_node=unwatched).exists()

    from packets.models import MtRawPacket

    MtRawPacket.objects.filter(from_int=700010).delete()
    update_learned_offline_thresholds()
    presence.refresh_from_db()
    assert presence.learned_offline_after_seconds is None
    assert presence.learned_offline_computed_at is not None
