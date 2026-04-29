# Recency, freshness, and cutoff thresholds

This document is the **authoritative reference** for every time-based cutoff
in Meshflow: how "online", "stale", "offline", "fresh", and "expired" are
decided across the API, Celery tasks, and downstream UIs.

Use it when:

- Adding a filter/annotation that depends on "recent" data.
- Changing behaviour around `last_heard`, `upload_time`, `triggered_at`, etc.
- Tuning an environment variable that controls a time window.
- Wiring a new UI that mirrors an API-side tier.

When you change any threshold in code, **update this file in the same PR**.

---

## Conventions

- All timestamps are timezone-aware (`timezone.now()`). See `AGENTS.md`.
- Defaults listed here are **code defaults**; operators can override via env
  vars (where indicated) or by editing `django_celery_beat.PeriodicTask` rows
  in admin (for Celery beat schedules).
- `ObservedNode.last_heard` is updated from `RawPacket.first_reported_time`
  in `packets/services/base.py` at ingest. It is the canonical "mesh heard"
  time.
- `PacketObservation.upload_time` (feeder upload) is the canonical
  "feeder heard" time for managed nodes. Traceroute **source eligibility** and
  constellation **coverage geometry** read the denormalized snapshot
  `ManagedNodeStatus` (refreshed periodically from packet observations).

---

## Summary: env vars that affect recency

Not all of these are listed in `docs/ENV_VARS.md` yet; this file is the
source of truth for defaults.

| Env var | Default | Purpose |
| --- | --- | --- |
| `PACKET_DEDUP_WINDOW_MINUTES` | `10` (min) | Packet dedup window vs `first_reported_time` |
| `SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS` | `600` (s) | Managed feeder snapshot (`ManagedNodeStatus`) + TR source eligibility window |
| `FAILED_TR_TIMEOUT_SECONDS` | `180` (s) | Mark stuck `AutoTraceRoute` as `failed` |
| `STALE_TR_TIMEOUT_SECONDS` | `180` (s) | Match inbound TR response packet to an `AutoTraceRoute` |
| `ONLINE_NODE_WINDOW_HOURS` | `2` (h) | `online_nodes` stats snapshot window |
| `MESH_MONITORING_VERIFICATION_SECONDS` | `180` (s) | Offline-verification window after a watch triggers |
| `MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS` | `3600` (s) | Min gap between verification-start Discord DMs |
| `MESH_MONITORING_NOTIFY_VERIFICATION_START` | unset = on | Toggle verification-start DMs |
| `AUTO_TR_SOURCE_SELECTION_ALGO` | `least_recently_used` | Source picker (uses `triggered_at` history) |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `1440` (24 h) | JWT access token TTL |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `30` | JWT refresh token TTL |
| `RF_PROPAGATION_POLL_MAX_SECONDS` | `300` | Max Site Planner poll budget per render |
| `RF_PROPAGATION_READY_RETENTION` | `3` | On-disk ready PNG retention count (not a duration) |

---

## `nodes/`

### Managed-node liveness (canonical)

Implemented in
[`Meshflow/nodes/managed_node_liveness.py`](../Meshflow/nodes/managed_node_liveness.py).

| Signal | Field | Fresh if | Controlled by |
| --- | --- | --- | --- |
| Feeder (TR sources / monitoring) | `ManagedNodeStatus.is_sending_data` | `True` when `last_packet_ingested_at` is within **`SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS`** (default **600 s / 10 min**) | env + periodic `nodes.tasks.update_managed_node_statuses` |
| Radio / mesh | `ObservedNode.last_heard` (or `ManagedNode.radio_last_heard` proxy) | within **2 h** (aligned with `online_nodes` window) | code |

`eligible_auto_traceroute_sources_queryset()` requires `allow_auto_traceroute`
and `status.is_sending_data`; the status row is derived from recent
`PacketObservation.upload_time` by the refresh task (same cutoff as the env
var above). This is the **canonical** rule for whether a managed node may
originate an auto or monitoring traceroute.

### Managed-node API annotations

In `ManagedNodeViewSet` (see `Meshflow/nodes/views.py`):

| Annotation | Window | Source |
| --- | --- | --- |
| `packets_last_hour` | **1 h** | `PacketObservation.upload_time` |
| `packets_last_24h` | **24 h** | `PacketObservation.upload_time` |
| `last_packet_ingested_at` | snapshot | `ManagedNodeStatus.last_packet_ingested_at` |
| `is_eligible_traceroute_source` | `allow_auto_traceroute` and `status.is_sending_data` | `ManagedNodeStatus` |

### Managed-node status denormalization (`ManagedNodeStatus`)

The `ManagedNodeStatus` model (`Meshflow/nodes/models.py`) stores a **snapshot** of
feeder/API ingestion state per `ManagedNode` (one-to-one). It is **not** mesh RF
liveness; that remains `ObservedNode.last_heard`.

| Field | Meaning | Source |
| --- | --- | --- |
| `last_packet_ingested_at` | Latest ingest time for this observer | `Max(PacketObservation.upload_time)` for `observer_id = ManagedNode.pk` |
| `is_sending_data` | Whether the observer is “currently feeding” per the same window as traceroute sources | `last_packet_ingested_at >= now - SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS` (default **600 s**) |
| `updated_at` | When the snapshot row was last written | set when the periodic task runs |

The Celery task `nodes.tasks.update_managed_node_statuses` runs on a **5-minute**
`django_celery_beat` interval (see `nodes` migration `0032_add_update_managed_node_statuses_periodic_task`).
Managed-node `include=status` responses use this snapshot for ingest time and
traceroute-source eligibility; packet-count fields remain live aggregates over
`PacketObservation`.

### `ObservedNodeViewSet.recent_counts`

Windows used by `/api/nodes/observed-nodes/recent_counts/` and the dashboard:

| Key | Window |
| --- | --- |
| `2` | 2 h |
| `24` | 24 h |
| `168` | 7 d |
| `720` | 30 d |
| `2160` | 90 d |

All against `ObservedNode.last_heard`.

### Weather list default

`/api/nodes/observed-nodes/weather/` defaults to
`latest_status.environment_reported_time >= now - 24h`. Clients can override
with the `environment_reported_after` query parameter.

### `ObservedNode.last_heard` source

Set from `RawPacket.first_reported_time` in
[`Meshflow/packets/services/base.py`](../Meshflow/packets/services/base.py).
Mesh monitoring, traceroute target selection, and all UI "online" tiers
depend on this.

---

## `packets/`

| Item | Default | Env | Purpose |
| --- | --- | --- | --- |
| `PACKET_DEDUP_WINDOW_MINUTES` | **10 min** | yes | `find_existing_packet` matches on `from_int` + `packet_id` + `first_reported_time ± window` |
| `STALE_TR_TIMEOUT_SECONDS` | **180 s** | yes | Match inbound traceroute response packets to a pending/sent/failed `AutoTraceRoute` by `triggered_at >= now - cutoff` |
| `RawPacket.first_reported_time`, `PacketObservation.upload_time` | `timezone.now()` | n/a | Ingestion timestamps; drive ordering, dedupe, liveness |

---

## `traceroute/`

### Lifecycle / staleness

| Item | Default | Env | Purpose |
| --- | --- | --- | --- |
| `FAILED_TR_TIMEOUT_SECONDS` | **180 s** | yes | Stale `AutoTraceRoute`: for `pending`, the clock is `earliest_send_at`; for `sent` with `dispatched_at` set, the clock is `dispatched_at`; for legacy `sent` rows without `dispatched_at`, `triggered_at` is used. Rows older than the window move to `failed` |
| Manual TR min interval (`MANUAL_TRIGGER_MIN_INTERVAL_SEC`) | **60 s** | no | Per-source rate limit on manual triggers (HTTP) |
| Monitoring TR min interval (`MONITORING_TRIGGER_MIN_INTERVAL_SEC`) | **30 s** | no | Default for `TRACEROUTE_DISPATCH_INTERVAL_SEC` (WebSocket send pacing per `ManagedNode`) |
| `TRACEROUTE_DISPATCH_INTERVAL_SEC` | same as `MONITORING_TRIGGER_MIN_INTERVAL_SEC` | yes | Min seconds between successful WebSocket sends for a given source (`traceroute.dispatch`) |
| `TRACEROUTE_MAX_PENDING_PER_SOURCE` | **20** | yes | New scheduler and mesh-monitoring rows are not created for a source with at least this many pending `AutoTraceRoute` rows |
| `TRACEROUTE_DISPATCH_CANDIDATE_BATCH` / `TRACEROUTE_DISPATCH_MAX_SCAN` | **200** / **10 000** | yes | Dispatcher paging when scanning due pending rows |

### Target selection

Implemented in
[`Meshflow/traceroute/target_selection.py`](../Meshflow/traceroute/target_selection.py).

| Parameter | Default | Purpose |
| --- | --- | --- |
| `last_heard_within_hours` | **3 h** | Candidate pool filter on `ObservedNode.last_heard` |
| Last-traced lookup window | **30 days** | `AutoTraceRoute.triggered_at` history considered for fairness |
| Demerit window | **24 h** | Candidates traced within the last 24 h get a scoring penalty |

### Strategy rotation

| Item | Default | Purpose |
| --- | --- | --- |
| `STRATEGY_LRU_TTL_SECONDS` | **30 days** (`60*60*24*30`) | Redis cache TTL for per-source strategy LRU keys (`cache.set` in `strategy_rotation.py`) |

### Source selection algorithm

`AUTO_TR_SOURCE_SELECTION_ALGO` (default `least_recently_used`) picks the
next source by `Max(triggered_at)` over recent `AutoTraceRoute` rows — this
is a time-based fairness mechanism even though there is no explicit cutoff.

### Analytics

| Item | Default | Purpose |
| --- | --- | --- |
| Dashboard `success_over_time` | **14 calendar days** | TR success chart window in `traceroute/views.py` |
| `backfill_traceroute_success_daily` | **30 days** default arg | Backfill span for `tr_success_daily` stats |
| `compute_reach` (`triggered_at_after`/`_before`) | caller-supplied | Reach / coverage aggregation; no implicit default window |

### Celery beat schedules

Seeded in migrations (operators can edit in admin):

| Task | Cadence |
| --- | --- |
| `schedule_traceroutes` | Every 2 h, minute `:00` UTC |
| `dispatch_pending_traceroutes` | Every 15 s | WebSocket send queue for `AutoTraceRoute` rows in `pending` (per-source pacing) |
| `mark_stale_traceroutes_failed` | Every minute |
| `collect_traceroute_success_daily` | Daily at `01:05` UTC |

---

## `mesh_monitoring/`

Node presence lifecycle:
`last_heard` silence → verification → offline confirmation.

| Item | Default | Env | Purpose |
| --- | --- | --- | --- |
| `NodeMonitoringConfig.last_heard_offline_after_seconds` | **21600 s (6 h)** (model default) | per-row | Silence threshold on `ObservedNode.last_heard` before verification starts |
| `DEFAULT_OFFLINE_AFTER_SECONDS` | **21600 s** | no | Fallback used when no `NodePresence` row exists (serializer + tasks) |
| `MESH_MONITORING_VERIFICATION_SECONDS` | **180 s** | yes | Window after `verification_started_at` to confirm the node is offline |
| `MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS` | **3600 s** | yes | Minimum gap between verification-start Discord DMs per watch |
| `MESH_MONITORING_NOTIFY_VERIFICATION_START` | on (unset) | yes | Feature flag for verification-start DMs |
| `MONITORING_TR_STAGGER_SECONDS` | **30 s** | no | Celery `countdown` between monitoring-triggered traceroutes |
| `process_node_watch_presence` beat | **every 60 s** | DB | Presence loop cadence |

**Historical note:** migration `0001` seeded `offline_after = 7200` (2 h)
on `NodeWatch`; migration `0006` moved the field to `NodePresence` with the
current default of **21600** (6 h). The 6 h default is canonical — treat the
2 h value as legacy.

---

## `stats/`

Hourly snapshots captured at **:05 UTC** for the **previous completed hour**.
Implemented in [`Meshflow/stats/tasks.py`](../Meshflow/stats/tasks.py).

| Item | Default | Env | Purpose |
| --- | --- | --- | --- |
| `ONLINE_NODE_WINDOW_HOURS` | **2 h** | yes | `online_nodes` snapshot window against `last_heard` / `rx_time` / `first_reported_time` |
| Snapshot lag | **1 h** | no | Snapshots target `current_hour - 1h` so only completed hours are recorded |
| `_collect_packet_volume` bucket | **1 h** | no | Packet volume snapshot uses `[recorded_at, recorded_at+1h)` on `first_reported_time` |
| `backfill_stats_snapshots` span | **30 days** default arg | no | Historical backfill |
| Stats API interval defaults | `interval=1`, `interval_type=hour` | query | Node/global stats endpoints |
| Stats API "month" unit | **30 days** | no | `get_interval_delta` month handling |

### Celery beat schedule

| Task | Cadence |
| --- | --- |
| `collect_stats_snapshots` | Every hour at `:05` UTC |

---

## `constellations/`

| Item | Default | Purpose |
| --- | --- | --- |
| `ENVELOPE_TTL_SECONDS` | **600 s** | Django cache TTL for computed constellation envelopes (`geometry.get_constellation_envelope`) |

---

## `rf_propagation/`

| Item | Default | Env | Purpose |
| --- | --- | --- | --- |
| `RF_PROPAGATION_POLL_MAX_SECONDS` | **300 s** | yes | Max time a worker polls the Site Planner engine per render |
| `_POLL_SCHEDULE_SECONDS` | tuple **1 s → 30 s** | no | Backoff schedule for engine status polling |
| `render_rf_propagation` soft/time limit | **600 s / 660 s** | no | Celery task limits |
| `render_rf_propagation` `retry_backoff_max` | **120 s** | no | Retry backoff cap |
| Failed render retention | **7 days** | no | `_run_retention` deletes `FAILED` rows with `created_at < now - 7d` |
| `RF_PROPAGATION_READY_RETENTION` | **3** | yes | On-disk ready PNG count per node (not a duration, listed for completeness) |

---

## `users/`

| Item | Default | Purpose |
| --- | --- | --- |
| Discord connect OAuth `STATE_MAX_AGE` | **900 s (15 min)** | Max age of signed OAuth connect state + cache key |
| `SIMPLE_JWT` access lifetime | **1440 min (24 h)** | JWT access token (env: `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`) |
| `SIMPLE_JWT` refresh lifetime | **30 days** | JWT refresh token (env: `JWT_REFRESH_TOKEN_LIFETIME_DAYS`) |

---

## `text_messages/`, `common/`, `ws/`

No time-based recency thresholds beyond inherited model timestamps.

---

## Celery periodic tasks (authoritative)

Schedules are persisted in the `django_celery_beat` database and seeded by
migrations. Operators can change intervals from Django admin without a
deploy; the table below lists the **seeded defaults**:

| Task | Cadence | Seed migration |
| --- | --- | --- |
| `schedule_traceroutes` | Every 2 h, `:00` UTC | `traceroute/migrations/0002_add_schedule_traceroutes_periodic_task.py` |
| `dispatch_pending_traceroutes` | Every 15 s | `traceroute/migrations/0011_traceroute_dispatch_queue.py` |
| `mark_stale_traceroutes_failed` | Every minute | `traceroute/migrations/0003_add_stale_tr_task_and_index.py` |
| `collect_traceroute_success_daily` | Daily `01:05` UTC | `traceroute/migrations/0006_add_collect_traceroute_success_daily_task.py` |
| `collect_stats_snapshots` | Hourly `:05` UTC | `stats/migrations/0002_add_collect_stats_snapshots_periodic_task.py` |
| `process_node_watch_presence` | Every 60 s | `mesh_monitoring/migrations/0002_add_process_node_watch_presence_periodic_task.py` |

---

## Cross-reference: UI (`meshtastic-bot-ui`)

These live in the UI repo and should stay aligned with the API tiers above.

### "My Nodes" page (`/nodes/my-nodes`)

Implemented in `src/lib/my-nodes-grouping.ts`.

**Claimed (non-managed) radios** — buckets from `ObservedNode.last_heard`:

| Bucket | Rule |
| --- | --- |
| Online | within **2 h** |
| Last heard recently | **> 2 h** and **≤ 7 d** |
| Offline | no `last_heard`, or **> 7 d** |

**Managed radios** — dual signal (must match API above):

| Signal | Field | Fresh if |
| --- | --- | --- |
| Feeder | `last_packet_ingested_at` | within **10 min** |
| Radio | `radio_last_heard` or `last_heard` | within **2 h** |

If both stale/missing → destructive "managed offline"; one stale → warning.

**GPS / position hints** use `latest_position.reported_time` with a **7-day**
cutoff (`>7d` = "stale"; missing coords or lat/lng `null`/`0` = "no GPS").

### Other UI locations

| Location | Field(s) | Thresholds |
| --- | --- | --- |
| `src/lib/reported-time-stale.ts` | any `reported_time` | `> 24h` → yellow (`stale24h`); `> 7d` → red (`stale7d`) |
| `src/lib/managed-node-status.ts` | `last_packet_ingested_at` | `≤ 10m` online; `≤ 1h` stale; `> 1h` offline; unset → `never` |
| `src/pages/nodes/NodesList.tsx` | `last_heard` filters | Presets 2 h / 24 h / 7 d / 30 d / all |
| `src/pages/Dashboard.tsx` | `last_heard` | 2 h, 24 h, 7 d, 30 d, 90 d (via API `recent_counts`) |
| `src/pages/nodes/MeshInfrastructure.tsx` | position `reported_time`, `last_heard` | Recent location ≤ 7 d; `OFFLINE` badge when `last_heard > 7d` |
| `meshtastic-bot` `src/persistence/node_info.py` | bot-local `last_heard` | `DEFAULT_ONLINE_THRESHOLD = 7200` (2 h online/offline split) |

---

## Changing a threshold

1. Update the constant / env default in the owning module.
2. Update tests (unit tests in the relevant app; integration tests if the
   change affects API responses).
3. If the threshold is also referenced in the UI, update
   `meshtastic-bot-ui/src/lib/my-nodes-grouping.ts` (or the owning module)
   and its tests in the same change window.
4. Update this file **and** `docs/ENV_VARS.md` if the env var surface
   changes. This document is the source of truth — keep it in sync.
