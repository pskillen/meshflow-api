from datetime import datetime, timedelta, timezone
from io import StringIO

from django.core.management import CommandError, call_command

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


def _mixed_rows(node):
    return [
        _dm(
            node,
            battery_level=0,
            voltage=0,
            meshtastic_channel_utilization=0,
            meshtastic_air_util_tx=0,
            uptime_seconds=0,
        ),
        _dm(node, voltage=0),
        _dm(node, battery_level=0, voltage=3.1),
        _dm(node, battery_level=0, voltage=None, uptime_seconds=0),
        _dm(node, battery_level=80, voltage=3.9, meshtastic_channel_utilization=0, uptime_seconds=0),
        _dm(node, meshtastic_channel_utilization=0, meshtastic_air_util_tx=0),
        _dm(node),
    ]


def _snapshot(model):
    return list(model.objects.order_by("pk").values_list("pk", *FIELDS))


@pytest.mark.django_db
def test_dry_run_counts_equal_real_counts_and_second_run_is_noop(create_observed_node):
    node = create_observed_node()
    _mixed_rows(node)
    for i in range(3):
        NodeLatestStatus.objects.update_or_create(
            node=create_observed_node(),
            defaults={"battery_level": 0, "voltage": i, "uptime_seconds": 0, "meshtastic_channel_utilization": 0},
        )
    before = _snapshot(DeviceMetrics)
    dry = _run("--dry-run", "--batch-size", "2")
    assert _snapshot(DeviceMetrics) == before
    real = _run("--batch-size", "2")
    assert dry.replace("[dry-run] ", "") == real
    assert "voltage (0): 0" not in real
    after = _snapshot(DeviceMetrics) + _snapshot(NodeLatestStatus)
    again = _run("--batch-size", "2")
    assert after == _snapshot(DeviceMetrics) + _snapshot(NodeLatestStatus)
    assert all(line.endswith(": 0") or line.endswith(":") for line in again.splitlines())


@pytest.mark.django_db
def test_batching_with_id_gaps(create_observed_node):
    node = create_observed_node()
    pks = []
    for _ in range(4):
        pks.append(_dm(node, voltage=0))
        for _ in range(3):
            DeviceMetrics.objects.create(node=node, voltage=1.0).delete()
    out = _run("--batch-size", "2")
    assert "voltage (0): 4" in out
    assert all(_vals(DeviceMetrics, pk)["voltage"] is None for pk in pks)


@pytest.mark.django_db
def test_before_on_node_latest_status(create_observed_node):
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old_node, new_node, null_node = create_observed_node(), create_observed_node(), create_observed_node()
    for n, when in ((old_node, cutoff - timedelta(days=1)), (new_node, cutoff + timedelta(days=1)), (null_node, None)):
        NodeLatestStatus.objects.update_or_create(node=n, defaults={"voltage": 0, "metrics_reported_time": when})
    _run("--before", cutoff.isoformat())
    assert NodeLatestStatus.objects.get(node=old_node).voltage is None
    assert NodeLatestStatus.objects.get(node=new_node).voltage == 0
    assert NodeLatestStatus.objects.get(node=null_node).voltage == 0


@pytest.mark.django_db
def test_node_latest_status_keeps_real_readings(create_observed_node):
    a, b = create_observed_node(), create_observed_node()
    NodeLatestStatus.objects.update_or_create(node=a, defaults={"battery_level": 0, "voltage": 3.1})
    NodeLatestStatus.objects.update_or_create(
        node=b, defaults={"battery_level": 80, "voltage": 3.9, "meshtastic_channel_utilization": 0}
    )
    _run()
    assert NodeLatestStatus.objects.get(node=a).battery_level == 0
    assert NodeLatestStatus.objects.get(node=b).meshtastic_channel_utilization == 0


@pytest.mark.django_db
@pytest.mark.parametrize("args", [["--batch-size", "0"], ["--before", "garbage"], ["--before", "2026-13-45T00:00:00Z"]])
def test_bad_arguments_raise_command_error(args):
    with pytest.raises(CommandError):
        _run(*args)
