"""Random auto TR target selection excludes mesh-monitoring suppressed nodes."""

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.models import NodePresence
from nodes.models import NodeLatestStatus
from traceroute.target_selection import pick_traceroute_target


@pytest.mark.django_db
def test_pick_traceroute_target_excludes_mesh_monitoring_suppressed(
    create_managed_node,
    create_observed_node,
    create_packet_observation,
):
    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=50.0,
        default_location_longitude=0.0,
    )
    create_packet_observation(observer=mn)

    obs = create_observed_node(node_id=998877665)
    obs.last_heard = timezone.now()
    obs.save(update_fields=["last_heard"])
    NodeLatestStatus.objects.create(node=obs, latitude=50.2, longitude=0.2)

    chosen = pick_traceroute_target(mn)
    assert chosen is not None

    NodePresence.objects.create(observed_node=obs, verification_started_at=timezone.now())
    assert pick_traceroute_target(mn) is None
