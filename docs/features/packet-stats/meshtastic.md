# Meshtastic packet statistics

Reverse-engineered from [`Meshflow/stats/`](../../../Meshflow/stats/) as of 2026-05. This is the reference for MeshCore parity ([#329](https://github.com/pskillen/meshflow-api/issues/329)).

## Overview

| Mechanism | Purpose | Storage |
| --- | --- | --- |
| **Hourly snapshots** (plus one daily, `node_firmware`) | Dashboard long-range charts, ops trending | `StatsSnapshot` rows |
| **Live API** | Ad-hoc charts, node detail pages, custom intervals | Computed per request from ORM |

**Replayed observations are excluded.** Stats over observations (`node_received_stats`, `node_neighbour_stats`,
the `online_nodes` and `new_nodes` snapshots) filter out `PacketObservation.replayed`, and a packet whose only
observations are replayed is not counted in `node_packet_stats` or `packet_volume` (2.8 connect-time replays are not
radio receptions). Feeder liveness (`ManagedNodeStatus` from `upload_time`) still counts them: the feeder really is
uploading.

**Non-radio observations are excluded from neighbour stats.** `node_neighbour_stats` also drops observations that
arrived over MQTT, UDP or the API (`via_mqtt`, or a `transport_mechanism` of `TRANSPORT_MQTT`, `TRANSPORT_MULTICAST_UDP`,
`TRANSPORT_UNICAST_UDP` or `TRANSPORT_API`), because they say nothing about who the feeder hears over the air. A null
transport counts as radio.

Snapshots favour **completed hours** and fixed JSON shapes. Live endpoints support `interval` + `interval_type` (hour/day/week/month) over user-supplied `start_date` / `end_date`.

---

## Celery: snapshot collection

### Schedule

| Item | Value |
| --- | --- |
| Task | `stats.tasks.collect_stats_snapshots` |
| Beat | Every hour at **minute :05 UTC** |
| Migration | [`stats/migrations/0002_add_collect_stats_snapshots_periodic_task.py`](../../../Meshflow/stats/migrations/0002_add_collect_stats_snapshots_periodic_task.py) |
| Backfill task | `stats.tasks.backfill_stats_snapshots` (default **30 days**) |
| Management command | `python manage.py backfill_stats_snapshots [--days N]` (add `--rewrite-online [--dry-run]` to correct existing online counts, see `online_nodes`) |

### “Previous completed hour” lag

When the task runs at e.g. `13:05 UTC`, it sets:

```text
current_hour = 13:00 UTC (floor)
hour_start   = 12:00 UTC  (= current_hour - 1h)
```

All snapshots for that run use `recorded_at = hour_start` (the **start** of the hour being summarized). The in-progress hour (`13:00–14:00`) is never written.

Each run assigns a shared **`run_id`** (`uuid4`) on every snapshot created in that execution.

### Idempotency

`_snapshot_exists(recorded_at, stat_type, constellation_id)` prevents duplicate rows. Backfill passes `skip_existing=True` so re-runs are safe.

---

## Snapshot types (Meshtastic)

| `stat_type` | Scope | `value` JSON shape |
| --- | --- | --- |
| `online_nodes` | Global + per-`Constellation` | `{"count": int, "window_hours": int}` |
| `packet_volume` | **Global only** | `{"count": int, "by_type": {…}}` |
| `new_nodes` | Global + per-`Constellation` | `{"count": int}` |
| `node_firmware` | **Global only, daily** | `{"count": int, "window_hours": int, "by_type": {…}, "by_basis": {…}}` |

`constellation_id` is `null` on the model for global scope.

### `online_nodes`

**Window:** the closed interval `[recorded_at - ONLINE_NODE_WINDOW_HOURS, recorded_at]` (env, default **2**). A point at `recorded_at` means "nodes heard in the 2 hours up to that time". `recorded_at` is the start of the hour the job records, and the job runs at `:05` an hour later, so a point lags real time by about 1 h 05.

| Scope | Query |
| --- | --- |
| Global | Distinct `from_int` on `MtRawPacket` with `first_reported_time` in the window, counting only packets with a non-replayed `PacketObservation` |
| Per-constellation | Distinct `packet__from_int` on non-replayed `PacketObservation` where `observer__constellation=…` and `rx_time` in the window |

The live job and the backfill use the same queries. Any transport (RF or MQTT) counts as heard; this differs from neighbour stats, which are RF-only.

**Why not `last_heard`:** it only moves forward, so a bound `last_heard <= recorded_at` would drop every node heard again after the snapshot hour. Counting from packets keeps those nodes in.

**Cut-over (api#501):** before this change the window had no upper bound (`>= recorded_at - 2h` only), so each point covered everything heard since then, up to the moment the job ran (about 3 h 05). Historic points therefore sit higher than new ones, and the online line steps down where the new rule begins unless the history is rewritten:

```bash
python manage.py backfill_stats_snapshots --rewrite-online --days 30 [--dry-run]
```

`--rewrite-online` recomputes `count` (and `window_hours`) on **existing** `online_nodes` and `mc_online_nodes` rows from raw packets. It never inserts rows, so the accepted snapshot gaps stay gaps, and it leaves a row alone when no raw packet exists in its window (recomputing would turn real history into zero). It is idempotent, and prints the earliest corrected hour and the earliest row that had raw packets, so you can see how far back the correction reaches. Rows older than the raw packets keep their old, higher values.

### `packet_volume`

**Bucket:** `[recorded_at, recorded_at + 1 hour)` on `MtRawPacket.first_reported_time`.

**Total:** count of rows in bucket after exclusions.

**`by_type` keys** (MTI subclass filters in `PACKET_TYPE_FILTERS`):

| Key | Filter |
| --- | --- |
| `text_message` | `messagepacket` present |
| `position` | `positionpacket` |
| `node_info` | `nodeinfopacket` |
| `device_metrics` | `devicemetricspacket` |
| `local_stats` | `localstatspacket` |
| `environment_metrics` | `environmentmetricspacket` |
| `traceroute` | `traceroutepacket` |

**Self-ingested device metrics exclusion:** rows where the packet is device metrics **and** every `PacketObservation` has `observer.meshtastic_node_id == packet.from_int` are excluded (feeder hearing only itself).

No per-constellation `packet_volume` snapshots exist for Meshtastic.

### `new_nodes`

Two modes:

| Mode | When | Global count |
| --- | --- | --- |
| **Hourly beat** | `collect_stats_snapshots` | `ObservedNode` with `created_at >= last_run_started_at` |
| **Backfill** | `for_backfill=True` | `created_at` in `[recorded_at, recorded_at + 1h)` |

`last_run_started_at` comes from the most recent **global** `new_nodes` snapshot’s `recorded_at` (`_get_last_run_started_at()`). First run uses `created_at__isnull=False` (all nodes with a timestamp).

**Per-constellation:** count `ObservedNode` rows whose `meshtastic_node_id` appears in `PacketObservation` from feeders in that constellation (with the same time filter as global — delta or hour window). Uses `meshtastic_node_id__in=observed_node_ids` from packet observations.

### `node_firmware`

Daily count of active Meshtastic nodes per firmware generation (see [inferred firmware](../packet-ingestion/inferred-firmware.md)).

- **`recorded_at`** is midnight UTC of the day the task runs (not the previous hour). `collect_stats_snapshots` writes it on the first hourly run of the day that finds it missing, normally `00:05`, so a late or failed run does not lose the day. A whole day with no successful run is not retried; re-run the backfill to fill the gap.
- **Window:** `ObservedNode` with `protocol=MESHTASTIC` and `last_heard >= recorded_at - 168h` (`ADOPTION_WINDOW_HOURS`). There is **no upper bound** on `last_heard`: it only moves forward, so a bound would drop a node heard just after midnight.
- **`by_type`:** open keys, one per stored `inferred_firmware` value; nodes with none are `unknown`. A new generation appears with no API change.
- **`by_basis`:** `key_identity`, `predicted_id`, `reported` (stored `feeder_report`: the node is one of our feeders and told us its own version) and `none` (null) are always present, at 0 if empty; any other stored basis passes through.
- A node that upgrades (new row) counts twice for up to 7 days.
- **Backfill:** `python manage.py backfill_node_firmware_snapshots [--days N] [--dry-run]` (default 90 days, idempotent). It does one `MtRawPacket` scan for `(day, from_int)` pairs and unions the 7 preceding days per target midnight, using today's classification. Backfilled days, including the current day's midnight, are derived from packets, not from `last_heard`, so a midnight written by the backfill before that day's `00:05` run can differ slightly from what the live run would have written; the live run then skips it. Packets whose only observations are 2.8 connect-time replays are not counted. It prints the scan size and time. `--dry-run` writes nothing but costs the same full scan, so run either form off-peak. Run it after `backfill_inferred_firmware`.

---

## Environment

| Variable | Default | Used by |
| --- | --- | --- |
| `ONLINE_NODE_WINDOW_HOURS` | `2` | `online_nodes` snapshot `window_hours` and window length |

See also [RECENCY.md](../../RECENCY.md) § `stats/`.

---

## HTTP API

Base path: `/api/stats/` ([`stats/urls.py`](../../../Meshflow/stats/urls.py)).

### Stored snapshots

| Endpoint | Auth | Query params |
| --- | --- | --- |
| `GET /api/stats/snapshots/` | Guest read | `stat_type`, `constellation_id` (`-1` = global), `recorded_at_after`, `recorded_at_before`, `bucket`, pagination |

Response: paginated `StatsSnapshot` (`id`, `recorded_at`, `stat_type`, `constellation_id`, `value`), newest first. Pages hold 100 rows by default and at most 1000 (`page_size`), so 90 days of hourly rows (2160) for one series span three pages at `page_size=1000`.

**`bucket=1d`** (the only bucket so far; `1h` and `6h` are reserved for the node-metric endpoints) returns one row per UTC day and constellation instead, computed at request time from the hourly rows. Nothing is stored. It needs `stat_type` and `recorded_at_after` (so a guest cannot ask for every hourly row since launch); any other `bucket`, a missing `stat_type` or `recorded_at_after`, or an unknown `stat_type` is a 400. A 90-day request for one series (`constellation_id` set, or `-1` for global) is 90 rows, one page at `page_size=1000`; without `constellation_id` it is `90 × (1 + constellations)` rows.

| `stat_type` | Daily `value.count` |
| --- | --- |
| `online_nodes`, `mc_online_nodes` (gauges) | mean of the day's hourly samples, rounded half up |
| `packet_volume`, `mc_packet_volume`, `new_nodes`, `mc_new_nodes` (flows) | sum; `by_type` summed per key |
| `node_firmware`, `tr_success_daily` (already daily) | unchanged rows, as without `bucket` |

Rolled rows have `id: null`, `recorded_at` at the UTC day start, and `value.samples`, the number of hourly rows that contributed (24 for a full day; fewer marks a partial day or a gap, which means are not corrected for). If `recorded_at_after` or `recorded_at_before` is not UTC midnight, the first and last days are partial (`samples` < 24). Gauge rows without a numeric `count` are skipped, not counted as samples. Code: [`stats/snapshot_rollup.py`](../../../Meshflow/stats/snapshot_rollup.py).

OpenAPI enum for `stat_type` today: `online_nodes`, `new_nodes`, `packet_volume`, `mc_online_nodes`, `mc_new_nodes`, `mc_packet_volume`, `node_firmware`, `tr_success_daily`.

### Live aggregation (Meshtastic `node_id` = decimal nodenum)

| Endpoint | Auth | Notes |
| --- | --- | --- |
| `GET /api/stats/global/` | Guest read | All `MtRawPacket`; one `packets` count per interval (no per-type breakdown) |
| `GET /api/stats/nodes/{node_id}/packets/` | Authenticated | Packets **from** node (`from_int`); per-type counts per interval; device-metrics exclusion |
| `GET /api/stats/nodes/{node_id}/received/` | Authenticated | `PacketObservation` as **managed** feeder; per-type by `rx_time` |
| `GET /api/stats/nodes/{node_id}/neighbours/` | Authenticated | Counts by source (relay or `from_int`); LSB ambiguity handling; excludes observations that arrived over MQTT, UDP or the API (null transport counts as radio) |

**Common query params** (`parse_stats_params`):

| Param | Default | Notes |
| --- | --- | --- |
| `interval` | `1` | Multiplier for truncation |
| `interval_type` | `hour` | `hour`, `day`, `week`, `month` |
| `start_date` / `end_date` | optional | ISO 8601 or `YYYY-MM-DD` |
| Month interval | — | Approximated as **30 days** in `get_interval_delta` |

Path param `node_id` is **Meshtastic numeric nodenum**; handlers filter `ObservedNode` / `ManagedNode` with `protocol=MESHTASTIC`.

---

## UI consumers (meshflow-ui)

| Component | API | `stat_type` / endpoint |
| --- | --- | --- |
| `MeshStatsSection` | Snapshots | `online_nodes`, `new_nodes`, `packet_volume` |
| `PacketStatsChartFromSnapshots` | `GET /api/stats/snapshots/?stat_type=packet_volume` | Global rows only (`constellation_id === null`) |
| `OnlineNodesChart` | Snapshots | `online_nodes` or `new_nodes` |
| `PacketStatsChart` / `PacketTypeChart` | Live | `GET /api/stats/global/` or per-node |
| Hooks | `useStatsSnapshots`, `usePacketStats` | [`usePacketStats.ts`](https://github.com/pskillen/meshflow-ui/blob/main/src/hooks/api/usePacketStats.ts) |

Client aggregates hourly snapshot points into 6 h / daily buckets ([`stats-aggregation.ts`](https://github.com/pskillen/meshflow-ui/blob/main/src/lib/stats-aggregation.ts)): `packet_volume` **sums** counts; `online_nodes` **averages** within a bucket.

---

## Operations

```bash
cd Meshflow && source ../venv/bin/activate

# Synchronous backfill (Celery task inline)
python manage.py backfill_stats_snapshots --days 30

# Or enqueue
# celery -A Meshflow call stats.tasks.backfill_stats_snapshots --kwargs='{"days": 30}'
```

**Verify recent snapshots:**

```bash
python manage.py shell -c "
from stats.models import StatsSnapshot
print(StatsSnapshot.objects.order_by('-recorded_at')[:5].values('recorded_at','stat_type','value'))
"
```

---

## Known gaps (Meshtastic doc scope)

- ~~Global `online_nodes` / `new_nodes` included MeshCore rows~~ — fixed ([#365](https://github.com/pskillen/meshflow-api/issues/365)) via `protocol=MESHTASTIC` filter on global ObservedNode queries.
- Live stats views do not accept MeshCore identity (pubkey / `internal_id`).
- `packet_volume` has no constellation-scoped snapshots.
- Traceroute success daily stats use a different `stat_type` (`tr_success_daily`) — not covered here.

See [meshcore.md](meshcore.md) for planned MC snapshot types.
