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
- `voltage` and `battery_level` ignore 0 (`ZERO_MEANS_MISSING_FIELDS`), because rows stored before null ingestion use 0 for a missing reading (see [Null readings](#null-readings)).
- `battery_level` ignores 101 (`POWERED_BATTERY_LEVEL`, "powered") unless every remaining reading is 101, in which case it is 101.
- `uptime_seconds` is the maximum (`MAX_FIELDS`).
- `wind_direction`, `rainfall_1h` and `rainfall_24h` are the latest reading in the bucket (`LAST_READING_FIELDS`); ties on `reported_time` fall back to `id`.
- 6h buckets are real (00, 06, 12, 18 UTC), computed in Python so SQLite tests and Postgres agree. `1d` starts at 00:00 UTC.

## Code anchors

- `NodeViewSet._metric_history` in [`nodes/views.py`](../../../Meshflow/nodes/views.py): parameter handling, shared by the three actions.
- `parse_bucket`, `bucket_start`, `bucket_rows` in `nodes/metric_buckets.py`.
- OpenAPI schemas `DeviceMetricBucket` and `EnvironmentMetricBucket` in [`openapi.yaml`](../../../openapi.yaml).

## Null readings

`DeviceMetrics` stores null for any field the device did not report. A value the device did report stays as reported, 0 included (a quiet channel really is 0% utilisation).

| Field | null | 0 |
|-------|------|---|
| `battery_level` | not reported | reported 0 (old rows: also "missing") |
| `voltage` | not reported | reported 0 (old rows: also "missing") |
| `meshtastic_channel_utilization` | not reported | reported 0% |
| `meshtastic_air_util_tx` | not reported | reported 0 |
| `uptime_seconds` | not reported | reported 0 |

- **Cut-over:** rows stored before this change use 0 for a missing reading. Bucketing keeps ignoring 0 voltage and 0 battery so old and new rows mix cleanly.
- **Cleaning old rows:** the owner runs `python manage.py null_placeholder_device_metrics` after deploy. Run it with `--dry-run --before <deploy time>` first, then for real off-peak. It nulls placeholder zeros in `DeviceMetrics` and `NodeLatestStatus` and is idempotent.
- **Options:** `--dry-run` writes nothing and prints the counts a real run would produce. `--batch-size` (default 5000) is the id range per transaction; each batch is one `UPDATE`, so a row is rewritten once. `--before` takes an ISO datetime and filters `logged_time` on `DeviceMetrics` and `metrics_reported_time` on `NodeLatestStatus` (rows with no reported time are skipped). Use the null-ingestion deploy time as the cutoff: the command finds the id range of matching rows first, and an old cutoff that matches few rows scans most of the table.
- **Without `--before`**, the command also nulls any all-zero or zero-voltage rows posted since the deploy, which is the bot still sending 0 for a missing value.

| Field | Nulled when it is 0 and |
|---|---|
| `voltage` | always |
| `battery_level` | voltage is 0 or null (a flat battery still reports volts) |
| `uptime_seconds` | always |
| `meshtastic_channel_utilization`, `meshtastic_air_util_tx` | both are 0 and battery, voltage and uptime are 0 too (an all-zero placeholder row); otherwise a 0 is a real reading and stays |

- Bucketing still ignores 0 voltage and 0 battery, so rows the command has not yet cleaned, or skipped via `--before`, mix cleanly with null ones. Dropping that exclusion is a later change, once the command has run on production.
- **Node upserts:** a feeder `device_metrics` block stores null for absent fields. A block with no metric values at all creates no `DeviceMetrics` row and leaves `NodeLatestStatus` metrics untouched. The bot still sends 0 for missing values until it is changed, so those rows keep a placeholder 0.
- **Telemetry packets:** a packet whose `deviceMetrics` carries none of the five fields creates no `DeviceMetrics` row, leaves `NodeLatestStatus` untouched and sends no `device_metrics_recorded` signal (the sender's `last_heard` still advances). A partial packet stores null for the missing fields, and `NodeLatestStatus` takes those nulls too.
- **MeshCore:** nothing writes `DeviceMetrics` for MeshCore, so nothing changes there.
- **Battery alerts:** a null battery reading is skipped by mesh monitoring.

## Decisions

All decided in https://github.com/pskillen/meshflow-ui/issues/407.

- Bucketed in Python, with real 6h buckets (Django's `Trunc` has no six-hour kind).
- Battery ignores 101 unless every reading is 101.
- Uptime is the maximum; wind direction and rainfall take the latest reading.
- Bucketed output is unpaginated.
- 0 voltage and 0 battery are excluded from means because rows stored before null ingestion use 0 for a missing reading.
- Dates without an offset are read as UTC.

## Known gaps

- Node upserts from the bot still send 0 for a missing reading until the bot is changed: https://github.com/pskillen/meshflow-bot/issues/170
- Queries filter `reported_time` but the index is `(node, -logged_time)`. The owner judged this fine on production.

## Related

- [packet-stats](../packet-stats/README.md): snapshot rollups use the same `bucket` vocabulary.
