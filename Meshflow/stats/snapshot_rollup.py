"""Request-time daily rollup of hourly ``StatsSnapshot`` rows.

Nothing is stored: the view reads the matching hourly rows once and aggregates
them per UTC day and constellation in Python.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

BUCKET_1D = "1d"
SUPPORTED_BUCKETS = (BUCKET_1D,)

# Hourly gauges: the daily value is the mean of the hourly samples.
GAUGE_STAT_TYPES = frozenset({"online_nodes", "mc_online_nodes"})
# Hourly flows: the daily value is the sum of the hourly samples.
FLOW_STAT_TYPES = frozenset({"packet_volume", "mc_packet_volume", "new_nodes", "mc_new_nodes"})
# Already one row per day: returned unchanged.
DAILY_STAT_TYPES = frozenset({"node_firmware", "tr_success_daily"})


def utc_day_start(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return 0


def _has_count(value: dict) -> bool:
    try:
        int(value.get("count"))
    except TypeError, ValueError:
        return False
    return True


def _sort_key(row: dict) -> tuple:
    cid = row["constellation_id"]
    return (row["recorded_at"], -1 if cid is None else cid)


def rollup_daily(stat_type: str, rows) -> list[dict]:
    """
    Aggregate ``(recorded_at, constellation_id, value)`` tuples per UTC day and constellation.

    Returns serializer-shaped dicts, newest day first. Gauges are averaged (rounded half up),
    flows summed (``by_type`` per key). ``value.samples`` is the number of hourly rows used
    (gauge rows without a numeric ``count`` are skipped).
    """
    is_gauge = stat_type in GAUGE_STAT_TYPES
    groups: dict[tuple[datetime, Optional[int]], dict] = defaultdict(lambda: {"count": 0, "samples": 0, "by_type": {}})

    for recorded_at, constellation_id, value in rows:
        value = value if isinstance(value, dict) else {}
        if is_gauge and not _has_count(value):
            continue
        group = groups[(utc_day_start(recorded_at), constellation_id)]
        group["count"] += _as_int(value.get("count"))
        group["samples"] += 1
        by_type = value.get("by_type")
        if isinstance(by_type, dict):
            for key, amount in by_type.items():
                group["by_type"][key] = group["by_type"].get(key, 0) + _as_int(amount)

    result = []
    for (day, constellation_id), group in groups.items():
        samples = group["samples"]
        if is_gauge:
            out = {"count": int(group["count"] / samples + 0.5), "samples": samples}
        else:
            out = {"count": group["count"], "samples": samples}
            if group["by_type"]:
                out["by_type"] = group["by_type"]
        result.append(
            {
                "id": None,
                "recorded_at": day,
                "stat_type": stat_type,
                "constellation_id": constellation_id,
                "value": out,
            }
        )

    result.sort(key=_sort_key, reverse=True)
    return result
