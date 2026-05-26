# Meshtastic packet statistics

Reverse-engineered from [`Meshflow/stats/`](../../../Meshflow/stats/) as of 2026-05. This is the reference for MeshCore parity ([#329](https://github.com/pskillen/meshflow-api/issues/329)).

## Overview

| Mechanism | Purpose | Storage |
| --- | --- | --- |
| **Hourly snapshots** | Dashboard long-range charts, ops trending | `StatsSnapshot` rows |
| **Live API** | Ad-hoc charts, node detail pages, custom intervals | Computed per request from ORM |

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
| Management command | `python manage.py backfill_stats_snapshots [--days N]` |

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

`constellation_id` is `null` on the model for global scope.

### `online_nodes`

**Window:** `threshold = recorded_at - ONLINE_NODE_WINDOW_HOURS` (env, default **2**). A node counts as “online” if heard at or after `threshold` relative to the snapshot hour boundary.

| Scope | Query (normal collection) |
| --- | --- |
| Global | `ObservedNode.objects.filter(last_heard__gte=threshold).count()` — **all protocols today** (MC nodes included if they have `last_heard`) |
| Per-constellation | Distinct `packet__from_int` on `PacketObservation` where `observer__constellation=…` and `rx_time__gte=threshold` |

**Backfill global variant:** `use_raw_packet_for_global=True` counts distinct `from_int` on `MtRawPacket` with `first_reported_time` in `[threshold, recorded_at]` instead of `last_heard`. Used when historical `last_heard` may not extend far enough (bulk-imported history).

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

---

## Environment

| Variable | Default | Used by |
| --- | --- | --- |
| `ONLINE_NODE_WINDOW_HOURS` | `2` | `online_nodes` snapshot `window_hours` and threshold |

See also [RECENCY.md](../../RECENCY.md) § `stats/`.

---

## HTTP API

Base path: `/api/stats/` ([`stats/urls.py`](../../../Meshflow/stats/urls.py)).

### Stored snapshots

| Endpoint | Auth | Query params |
| --- | --- | --- |
| `GET /api/stats/snapshots/` | Guest read | `stat_type`, `constellation_id` (`-1` = global), `recorded_at_after`, `recorded_at_before`, pagination |

Response: paginated `StatsSnapshot` (`recorded_at`, `stat_type`, `constellation_id`, `value`).

OpenAPI enum for `stat_type` today: `online_nodes`, `new_nodes`, `packet_volume`.

### Live aggregation (Meshtastic `node_id` = decimal nodenum)

| Endpoint | Auth | Notes |
| --- | --- | --- |
| `GET /api/stats/global/` | Guest read | All `MtRawPacket`; one `packets` count per interval (no per-type breakdown) |
| `GET /api/stats/nodes/{node_id}/packets/` | Authenticated | Packets **from** node (`from_int`); per-type counts per interval; device-metrics exclusion |
| `GET /api/stats/nodes/{node_id}/received/` | Authenticated | `PacketObservation` as **managed** feeder; per-type by `rx_time` |
| `GET /api/stats/nodes/{node_id}/neighbours/` | Authenticated | Counts by source (relay or `from_int`); LSB ambiguity handling |

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
