from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

import pytest

from nodes.models import NodeLatestStatus, Position
from packets.models import PositionPacket


def _run(*args):
    out = StringIO()
    call_command("cleanup_null_island_positions", *args, stdout=out)
    return out.getvalue()


def _position(node, lat, lon, age_minutes=0, **kwargs):
    return Position.objects.create(
        node=node,
        reported_time=timezone.now() - timedelta(minutes=age_minutes),
        latitude=lat,
        longitude=lon,
        **kwargs,
    )


def _packet(lat, lon, packet_id):
    return PositionPacket.objects.create(
        packet_id=packet_id,
        from_int=987654321,
        from_str="!3ade68b1",
        port_num="POSITION_APP",
        latitude=lat,
        longitude=lon,
    )


@pytest.fixture
def broken_node(create_observed_node):
    """A node with a valid older fix, then 0,0 broadcasts, and a status stuck at 0,0."""
    node = create_observed_node()
    _position(node, 51.5, -0.1, age_minutes=60, altitude=12.0)
    _position(node, 52.0, -1.0, age_minutes=30, altitude=34.0)
    _position(node, 0.0, 0.0, age_minutes=10)
    _position(node, 5e-8, -5e-8, age_minutes=5)
    NodeLatestStatus.objects.create(node=node, latitude=0.0, longitude=0.0, altitude=0.0)
    return node


@pytest.mark.django_db
def test_dry_run_reports_and_changes_nothing(broken_node):
    _packet(0.0, 0.0, 1)
    out = _run()
    assert "Dry run" in out
    assert "Position rows at 0,0 would be deleted: 2" in out
    assert "NodeLatestStatus rows at 0,0 would be repaired: 1 (1 restored" in out
    assert "PositionPacket rows at 0,0 would be nulled: 1" in out
    assert Position.objects.count() == 4
    status = NodeLatestStatus.objects.get(node=broken_node)
    assert (status.latitude, status.longitude) == (0.0, 0.0)
    assert PositionPacket.objects.get().latitude == 0.0


@pytest.mark.django_db
def test_apply_deletes_and_restores_newest_valid_position(broken_node):
    _packet(0.0, 0.0, 1)
    _packet(51.5, -0.1, 2)
    out = _run("--apply", "--batch-size", "1")
    assert "Position rows at 0,0 deleted: 2" in out
    assert Position.objects.count() == 2
    status = NodeLatestStatus.objects.get(node=broken_node)
    assert (status.latitude, status.longitude, status.altitude) == (52.0, -1.0, 34.0)
    assert status.position_reported_time is not None
    nulled = PositionPacket.objects.get(packet_id=1)
    assert (nulled.latitude, nulled.longitude) == (None, None)
    kept = PositionPacket.objects.get(packet_id=2)
    assert (kept.latitude, kept.longitude) == (51.5, -0.1)


@pytest.mark.django_db
def test_apply_nulls_status_when_no_valid_position_remains(create_observed_node):
    node = create_observed_node()
    _position(node, 0.0, 0.0)
    NodeLatestStatus.objects.create(node=node, latitude=0.0, longitude=0.0, altitude=0.0, ground_speed=1.0)
    _run("--apply")
    assert Position.objects.count() == 0
    status = NodeLatestStatus.objects.get(node=node)
    assert status.latitude is None and status.longitude is None
    assert status.altitude is None and status.ground_speed is None


@pytest.mark.django_db
def test_second_run_does_nothing(broken_node):
    _packet(0.0, 0.0, 1)
    _run("--apply")
    out = _run("--apply")
    assert "Position rows at 0,0 deleted: 0" in out
    assert "repaired: 0" in out
    assert "nulled: 0" in out


@pytest.mark.django_db
def test_real_positions_and_statuses_are_untouched(create_observed_node):
    node = create_observed_node()
    _position(node, 0.0, 12.3)
    _position(node, 12.3, 0.0)
    NodeLatestStatus.objects.create(node=node, latitude=12.3, longitude=0.0)
    _packet(0.0, 12.3, 1)
    _run("--apply")
    assert Position.objects.count() == 2
    status = NodeLatestStatus.objects.get(node=node)
    assert (status.latitude, status.longitude) == (12.3, 0.0)
    assert PositionPacket.objects.get().longitude == 12.3
