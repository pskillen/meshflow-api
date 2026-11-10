# Node metrics history

**Status:** Done · **Tracking:** https://github.com/pskillen/meshflow-ui/issues/407

## Purpose

History of device, environment and power telemetry per observed node, for node pages. Each reading is a row (`DeviceMetrics`, `EnvironmentMetrics`, `PowerMetrics`) keyed by node and `reported_time`. The endpoints return the raw rows, or roll them up into UTC buckets with `bucket`.

## Endpoints

All on `NodeViewSet`, under `/api/nodes/observed-nodes/{internal_id}/`, authenticated.

| Endpoint | Model |
| --- | --- |
| `GET device_metrics/` | `DeviceMetrics` |
| `GET environment_metrics/` | `EnvironmentMetrics` |
| `GET power_metrics/` | `PowerMetrics` |

| Param | Notes |
| --- | --- |
| `start_date` | ISO 8601 or `YYYY-MM-DD`; filters `reported_time >=` |
| `end_date` | ISO 8601 or `YYYY-MM-DD`; widened to 23:59:59 of its day, then filters `reported_time <=` |
| `bucket` | `1h`, `6h` or `1d`; empty means unbucketed; anything else is a 400 |

Without `bucket` the response is the serializer's rows, newest first. The bulk `device_metrics` and `environment_metrics` endpoints (several nodes at once) do not take `bucket` and do not follow these rules.

## Bucketing rules

Constants are in [`nodes/metric_buckets.py`](../../../Meshflow/nodes/metric_buckets.py).

- One row per populated UTC bucket, newest first, **unpaginated**. `reported_time` is the bucket start, `node` is the node id, and `samples` is the number of raw rows in the bucket.
- A field is the mean of its non-null readings, or null when there were none.
- `voltage` and `battery_level` ignore 0 (`ZERO_MEANS_MISSING_FIELDS`), because ingestion stores a missing reading as 0.
- `battery_level` ignores 101 (`POWERED_BATTERY_LEVEL`, "powered") unless every remaining reading is 101, in which case it is 101.
- `uptime_seconds` is the maximum (`MAX_FIELDS`).
- `wind_direction`, `rainfall_1h` and `rainfall_24h` are the latest reading in the bucket (`LAST_READING_FIELDS`); ties on `reported_time` fall back to `id`.
- 6h buckets are real (00, 06, 12, 18 UTC), computed in Python so SQLite tests and Postgres agree. `1d` starts at 00:00 UTC.

## Code anchors

- `NodeViewSet._metric_history` in [`nodes/views.py`](../../../Meshflow/nodes/views.py): parameter handling, shared by the three actions.
- `parse_bucket`, `bucket_start`, `bucket_rows` in `nodes/metric_buckets.py`.
- OpenAPI schemas `DeviceMetricBucket` and `EnvironmentMetricBucket` in [`openapi.yaml`](../../../openapi.yaml).

## Decisions

All decided in https://github.com/pskillen/meshflow-ui/issues/407.

- Bucketed in Python, with real 6h buckets (Django's `Trunc` has no six-hour kind).
- Battery ignores 101 unless every reading is 101.
- Uptime is the maximum; wind direction and rainfall take the latest reading.
- Bucketed output is unpaginated.
- 0 voltage and 0 battery are excluded from means because ingestion stores missing as 0.

## Known gaps

- Zeros stored for missing readings: https://github.com/pskillen/meshflow-api/issues/524
- Dates without an offset parse as naive datetimes and raise a RuntimeWarning: https://github.com/pskillen/meshflow-api/issues/525
- Queries filter `reported_time` but the index is `(node, -logged_time)`. The owner judged this fine on production.

## Related

- [packet-stats](../packet-stats/README.md): snapshot rollups use the same `bucket` vocabulary.
