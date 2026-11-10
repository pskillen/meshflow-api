from datetime import datetime, timedelta, timezone
from io import StringIO

from django.core.management import call_command

import pytest

from nodes.models import DeviceMetrics, NodeLatestStatus

FIELDS = ["battery_level", "voltage", "meshtastic_channel_utilization", "meshtastic_air_util_tx", "uptime_seconds"]


def _dm(node, when=None, **kw):
    values = {f: None for f in FIELDS}
    values.update(kw)
    row = DeviceMetrics.objects.create(node=node, **values)
    if when is not None:
        DeviceMetrics.objects.filter(pk=row.pk).update(logged_time=when)
    return row.pk


def _vals(model, pk):
    return {f: getattr(model.objects.get(pk=pk), f) for f in FIELDS}


def _run(*args):
    out = StringIO()
    call_command("null_placeholder_device_metrics", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_all_zero_row_is_nulled(create_observed_node):
    pk = _dm(
        create_observed_node(),
        battery_level=0,
        voltage=0,
        meshtastic_channel_utilization=0,
        meshtastic_air_util_tx=0,
        uptime_seconds=0,
    )
    _run()
    assert _vals(DeviceMetrics, pk) == {f: None for f in FIELDS}


@pytest.mark.django_db
def test_voltage_zero_nulled_and_other_values_kept(create_observed_node):
    pk = _dm(create_observed_node(), battery_level=80, voltage=0, meshtastic_channel_utilization=5, uptime_seconds=100)
    _run()
    assert _vals(DeviceMetrics, pk) == {
        "battery_level": 80,
        "voltage": None,
        "meshtastic_channel_utilization": 5,
        "meshtastic_air_util_tx": None,
        "uptime_seconds": 100,
    }


@pytest.mark.django_db
def test_battery_zero_nulled_when_voltage_zero_or_null(create_observed_node):
    node = create_observed_node()
    zero_v = _dm(node, battery_level=0, voltage=0, uptime_seconds=50)
    null_v = _dm(node, battery_level=0, voltage=None)
    _run()
    assert _vals(DeviceMetrics, zero_v)["battery_level"] is None
    assert _vals(DeviceMetrics, null_v)["battery_level"] is None


@pytest.mark.django_db
def test_battery_zero_kept_when_voltage_reported(create_observed_node):
    pk = _dm(create_observed_node(), battery_level=0, voltage=3.1)
    _run()
    assert _vals(DeviceMetrics, pk)["battery_level"] == 0
    assert _vals(DeviceMetrics, pk)["voltage"] == 3.1


@pytest.mark.django_db
def test_channel_zero_kept_with_real_battery(create_observed_node):
    pk = _dm(
        create_observed_node(),
        battery_level=80,
        voltage=3.9,
        meshtastic_channel_utilization=0,
        meshtastic_air_util_tx=0,
        uptime_seconds=0,
    )
    _run()
    vals = _vals(DeviceMetrics, pk)
    assert vals["meshtastic_channel_utilization"] == 0
    assert vals["meshtastic_air_util_tx"] == 0
    assert vals["battery_level"] == 80
    assert vals["uptime_seconds"] is None


@pytest.mark.django_db
def test_node_latest_status_is_covered(create_observed_node):
    node = create_observed_node()
    NodeLatestStatus.objects.update_or_create(
        node=node,
        defaults={
            "battery_level": 0,
            "voltage": 0,
            "meshtastic_channel_utilization": 0,
            "meshtastic_air_util_tx": 0,
            "uptime_seconds": 0,
        },
    )
    _run()
    status_row = NodeLatestStatus.objects.get(node=node)
    assert all(getattr(status_row, f) is None for f in FIELDS)


@pytest.mark.django_db
def test_before_limits_rows(create_observed_node):
    node = create_observed_node()
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old = _dm(node, when=cutoff - timedelta(days=1), voltage=0)
    new = _dm(node, when=cutoff + timedelta(days=1), voltage=0)
    _run("--before", cutoff.isoformat())
    assert _vals(DeviceMetrics, old)["voltage"] is None
    assert _vals(DeviceMetrics, new)["voltage"] == 0


@pytest.mark.django_db
def test_dry_run_writes_nothing_and_reports_counts(create_observed_node):
    pk = _dm(create_observed_node(), battery_level=0, voltage=0, uptime_seconds=0)
    out = _run("--dry-run")
    assert _vals(DeviceMetrics, pk)["voltage"] == 0
    assert "[dry-run] DeviceMetrics:" in out
    assert "voltage (0): 1" in out


@pytest.mark.django_db
def test_idempotent_and_batched(create_observed_node):
    node = create_observed_node()
    for _ in range(5):
        _dm(node, voltage=0, uptime_seconds=0)
    first = _run("--batch-size", "2")
    assert "voltage (0): 5" in first
    second = _run("--batch-size", "2")
    assert "voltage (0): 0" in second
    assert "uptime_seconds (0): 0" in second
