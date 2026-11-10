"""Server-side bucketing for node metric history (device, environment, power).

Rows are rolled up in Python rather than in SQL so the same code runs on SQLite
(tests) and PostgreSQL (deployed), and so six-hour buckets are real (Django's
``Trunc`` has no six-hour kind). Buckets are aligned to UTC.
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Iterable, Sequence

BUCKET_CHOICES = ("1h", "6h", "1d")

#: Battery level reported by powered (non-battery) devices.
POWERED_BATTERY_LEVEL = 101

#: Rows stored before null ingestion use 0 for a missing reading, so 0 is excluded from the mean.
#: Channel utilisation, air time and uptime are not listed: a real 0 is possible there.
ZERO_MEANS_MISSING_FIELDS = frozenset({"voltage", "battery_level"})

#: Fields where the bucket value is the most recent reading, not a mean.
LAST_READING_FIELDS = frozenset({"wind_direction", "rainfall_1h", "rainfall_24h"})

#: Fields where the bucket value is the maximum.
MAX_FIELDS = frozenset({"uptime_seconds"})


def parse_bucket(value):
    """Return the validated bucket string, ``None`` when absent, or raise ``ValueError``."""
    if value is None or value == "":
        return None
    if value not in BUCKET_CHOICES:
        raise ValueError(f"Invalid bucket. Use one of: {', '.join(BUCKET_CHOICES)}.")
    return value


def bucket_start(moment: datetime, bucket: str) -> datetime:
    """Floor ``moment`` to the start of its UTC bucket."""
    moment = moment.astimezone(dt_timezone.utc)
    if bucket == "1h":
        return moment.replace(minute=0, second=0, microsecond=0)
    if bucket == "6h":
        return moment.replace(hour=moment.hour // 6 * 6, minute=0, second=0, microsecond=0)
    if bucket == "1d":
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unknown bucket {bucket!r}")


def _mean(values: Sequence[float]):
    return sum(values) / len(values) if values else None


def _aggregate_field(field: str, values: Sequence):
    """Aggregate one field's readings (ascending by time, nulls included)."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    if field in LAST_READING_FIELDS:
        return values[-1]
    if field in MAX_FIELDS:
        return max(values)
    if field in ZERO_MEANS_MISSING_FIELDS:
        values = [v for v in values if v != 0]
        if not values:
            return None
    if field == "battery_level":
        real = [v for v in values if v != POWERED_BATTERY_LEVEL]
        return _mean(real) if real else POWERED_BATTERY_LEVEL
    return _mean(values)


def bucket_rows(rows: Iterable[dict], fields: Sequence[str], bucket: str) -> list[dict]:
    """Roll ``rows`` (dicts with ``node_id``, ``reported_time`` and optionally ``id``) up into buckets.

    Returns one dict per populated bucket, newest first (matching the unbucketed
    ordering): ``node``, ``reported_time`` (bucket start), ``samples`` and each
    field in ``fields``.
    """
    groups: dict[datetime, list[dict]] = {}
    for row in rows:
        groups.setdefault(bucket_start(row["reported_time"], bucket), []).append(row)

    result = []
    for start in sorted(groups, reverse=True):
        # Ties on reported_time fall back to id so "latest" is deterministic.
        group = sorted(groups[start], key=lambda r: (r["reported_time"], r.get("id", 0)))
        out = {"node": group[0]["node_id"], "reported_time": start, "samples": len(group)}
        for field in fields:
            out[field] = _aggregate_field(field, [r[field] for r in group])
        result.append(out)
    return result
