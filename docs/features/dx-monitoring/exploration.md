# DX Traceroute Exploration

Phase 4 of DX Monitoring queues **bounded** traceroute exploration for **active** `DxEvent` rows while an event is still within its window. This reuses the shared `AutoTraceRoute` dispatch queue ([meshflow-api #221](https://github.com/pskillen/meshflow-api/issues/221)).

## Model

`DxEventTraceroute` links an event to an `AutoTraceRoute` (DX watch, or a linked **New node baseline** row) and records outcomes: pending until a terminal traceroute result, completed, failed, or skipped with a documented reason (no source, cooldowns, duplicate, fan-out cap, destination excluded from detection, and so on).

## Producer behaviour

The periodic Celery task `dx_monitoring.tasks.explore_active_dx_events` runs every two minutes (see migrations). It calls planning logic that:

1. Selects active events whose **last exploration attempt** (`max(created_at)` on related `DxEventTraceroute` rows) is older than the configured **event cooldown**, or have never been attempted.
2. For each event, prefers `last_observer` as a traceroute source when it is eligible, then same-constellation sources ordered by distance to the destination, then the global eligible source list used by the automatic scheduler.
3. **Dedupes** against `NEW_NODE_BASELINE` rows: pending or in-flight baselines for the same target/source are **linked** to the event instead of queueing a duplicate `DX_WATCH`. Recently **completed** baselines are linked as completed evidence without sending another command. Recently **failed** baselines are treated like a cooldown before `DX_WATCH` from the same source.
4. Queues at most `DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT` distinct source perspectives per planning cycle that are not already covered.
5. Applies **target** and **source** cooldowns against prior `DX_WATCH` rows with `trigger_source=dx_monitoring`, and respects `TRACEROUTE_MAX_PENDING_PER_SOURCE` before creating new rows.

## Completion and detection

When a traceroute response completes, `TraceroutePacketService` still runs `maybe_detect_dx_from_completed_traceroute` for distant-hop detection. For hops whose destination matches an active exploration link on the same `AutoTraceRoute`, detection **skips** creating duplicate `traceroute_distant_hop` packet evidence; route summaries remain on the `DxEventTraceroute` row. After that, `on_auto_traceroute_exploration_finished` marks linked `DxEventTraceroute` rows completed or failed. Stale failed `AutoTraceRoute` rows from timeout processing call the same hook so linked rows do not stay pending forever.

## Configuration

See **[docs/ENV_VARS.md](../../ENV_VARS.md)** (DX Monitoring exploration) and **[docs/features/traceroute/queuing.md](../traceroute/queuing.md)** for interaction with new-node baseline and other queue producers.
