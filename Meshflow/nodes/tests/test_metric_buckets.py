from datetime import datetime, timezone

import pytest

from nodes.metric_buckets import bucket_rows, bucket_start, parse_bucket


def _t(h, m=0, day=1):
    return datetime(2026, 1, day, h, m, tzinfo=timezone.utc)


def _row(t, **kw):
    return {"node_id": 1, "reported_time": t, **kw}


def test_parse_bucket():
    assert parse_bucket(None) is None
    assert parse_bucket("") is None
    assert parse_bucket("6h") == "6h"
    with pytest.raises(ValueError):
        parse_bucket("2h")


def test_bucket_start_boundaries():
    assert bucket_start(_t(5, 59), "1h") == _t(5)
    assert bucket_start(_t(5, 59), "6h") == _t(0)
    assert bucket_start(_t(6, 0), "6h") == _t(6)
    assert bucket_start(_t(23, 59), "6h") == _t(18)
    assert bucket_start(_t(23, 59), "1d") == _t(0)


def test_mean_ignores_nulls_and_counts_samples():
    rows = [_row(_t(1), voltage=3.0), _row(_t(2), voltage=None), _row(_t(3), voltage=4.0)]
    (out,) = bucket_rows(rows, ["voltage"], "6h")
    assert out["voltage"] == 3.5
    assert out["samples"] == 3
    assert out["reported_time"] == _t(0)


def test_all_null_is_none():
    (out,) = bucket_rows([_row(_t(1), voltage=None)], ["voltage"], "1h")
    assert out["voltage"] is None


def test_battery_101_handling():
    mixed = [_row(_t(1), battery_level=101), _row(_t(2), battery_level=80), _row(_t(3), battery_level=60)]
    assert bucket_rows(mixed, ["battery_level"], "1d")[0]["battery_level"] == 70
    powered = [_row(_t(1), battery_level=101), _row(_t(2), battery_level=101)]
    assert bucket_rows(powered, ["battery_level"], "1d")[0]["battery_level"] == 101


def test_zero_voltage_is_missing_not_averaged():
    rows = [_row(_t(1), voltage=0), _row(_t(2), voltage=4.0)]
    (out,) = bucket_rows(rows, ["voltage"], "6h")
    assert out["voltage"] == 4.0
    assert out["samples"] == 2
    zeros = [_row(_t(1), voltage=0), _row(_t(2), voltage=0)]
    assert bucket_rows(zeros, ["voltage"], "6h")[0]["voltage"] is None


def test_zero_battery_level_is_missing_not_averaged():
    rows = [_row(_t(1), battery_level=0), _row(_t(2), battery_level=80)]
    assert bucket_rows(rows, ["battery_level"], "1d")[0]["battery_level"] == 80
    zeros = [_row(_t(1), battery_level=0), _row(_t(2), battery_level=0)]
    assert bucket_rows(zeros, ["battery_level"], "1d")[0]["battery_level"] is None
    # 0 and 101 together: 0 is dropped, the powered marker remains.
    both = [_row(_t(1), battery_level=0), _row(_t(2), battery_level=101)]
    assert bucket_rows(both, ["battery_level"], "1d")[0]["battery_level"] == 101


def test_mixed_old_zero_new_null_and_real_rows():
    real = [_row(_t(3), battery_level=80, voltage=4.0), _row(_t(4), battery_level=60, voltage=3.8)]
    legacy_zero = [_row(_t(1), battery_level=0, voltage=0)]
    new_null = [_row(_t(2), battery_level=None, voltage=None)]
    fields = ["battery_level", "voltage"]
    (expected,) = bucket_rows(real, fields, "1d")
    (mixed,) = bucket_rows(legacy_zero + new_null + real, fields, "1d")
    assert mixed["battery_level"] == expected["battery_level"] == 70
    assert mixed["voltage"] == expected["voltage"]


def test_zero_kept_for_other_fields():
    rows = [
        _row(_t(1), meshtastic_channel_utilization=0, uptime_seconds=0),
        _row(_t(2), meshtastic_channel_utilization=10, uptime_seconds=0),
    ]
    (out,) = bucket_rows(rows, ["meshtastic_channel_utilization", "uptime_seconds"], "1d")
    assert out["meshtastic_channel_utilization"] == 5
    assert out["uptime_seconds"] == 0


def test_uptime_max_and_last_reading_fields():
    rows = [
        _row(_t(3), uptime_seconds=50, wind_direction=270, rainfall_1h=None),
        _row(_t(1), uptime_seconds=100, wind_direction=90, rainfall_1h=2.0),
        _row(_t(2), uptime_seconds=10, wind_direction=180, rainfall_1h=1.0),
    ]
    (out,) = bucket_rows(rows, ["uptime_seconds", "wind_direction", "rainfall_1h"], "1d")
    assert out["uptime_seconds"] == 100
    assert out["wind_direction"] == 270  # latest reading, not an angle average
    assert out["rainfall_1h"] == 1.0  # latest non-null reading


def test_buckets_split_and_ordered_newest_first():
    rows = [_row(_t(5, 59), voltage=1.0), _row(_t(6, 0), voltage=2.0), _row(_t(7), voltage=4.0)]
    out = bucket_rows(rows, ["voltage"], "6h")
    assert [o["reported_time"] for o in out] == [_t(6), _t(0)]
    assert [o["voltage"] for o in out] == [3.0, 1.0]


def test_last_reading_ties_break_on_id():
    t = _t(1)
    rows = [
        _row(t, id=7, wind_direction=70),
        _row(t, id=9, wind_direction=90),
        _row(t, id=8, wind_direction=80),
    ]
    (out,) = bucket_rows(rows, ["wind_direction"], "1h")
    assert out["wind_direction"] == 90
    (out,) = bucket_rows(list(reversed(rows)), ["wind_direction"], "1h")
    assert out["wind_direction"] == 90
