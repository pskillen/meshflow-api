# Traceroute Areas of Concern

This note records the intended ownership boundaries for traceroute-related
behaviour. It exists because traceroute is both a mission-critical operational
primitive and the data source for richer analytics and visualisation features.

The short version:

- `traceroute` owns the durable traceroute lifecycle.
- Operational apps such as `mesh_monitoring` and `dx_monitoring` own their own
product decisions, but request traceroutes through the core traceroute
boundary.
- Analytics and visualisation should move out of the core app so graph, map,
and reporting work can evolve without increasing risk to ingestion,
dispatch, monitoring, or DX workflows.

## Functional Areas


| Functional area                        | Final app / owner                               | Rationale                                                                                                                                                                                                                                     |
| -------------------------------------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core traceroute domain                 | `traceroute`                                    | `AutoTraceRoute`, `TriggerType`, status transitions, route payloads, dispatch metadata, and model constraints are the shared operational substrate. Moving the model would add migration churn without improving the boundary.                |
| Manual traceroute API                  | `traceroute`                                    | Manual trigger, list, detail, `can_trigger`, and triggerable-node endpoints are direct operations on `AutoTraceRoute` and its permission model.                                                                                               |
| Traceroute scheduling                  | `traceroute`                                    | Periodic mesh exploration is a generic traceroute producer. It should use the same source eligibility, target selection, strategy rotation, pending caps, and dispatch queue as other producers.                                              |
| Dispatch queue and stale timeout       | `traceroute`                                    | Pending/sent/completed/failed lifecycle, per-source pacing, retry state, timeout handling, and WebSocket status notifications are core lifecycle concerns used by all producers.                                                              |
| Packet completion integration          | `packets` + `traceroute`                        | `packets` owns packet parsing and ingestion. `traceroute` should own matching/finalising `AutoTraceRoute` rows and emitting lifecycle side effects through a stable service boundary.                                                         |
| New-node baseline traceroutes          | `traceroute`                                    | A first-seen node baseline is a generic operational traceroute, not a user watch and not analytics. It establishes route evidence once per target and is reused by DX exploration dedupe logic, so it belongs with the core lifecycle.        |
| Mesh watch and node monitoring         | `mesh_monitoring`                               | Watches, presence state, offline verification, watcher notifications, and monitoring-specific source selection are product concerns of mesh monitoring. The app should request `NODE_WATCH` traceroutes through the core traceroute boundary. |
| DX monitoring and exploration          | `dx_monitoring`                                 | DX event detection, exploration planning, skip reasons, event linking, and DX notifications are product concerns of DX monitoring. The app should request `DX_WATCH` traceroutes through the core traceroute boundary.                        |
| Source liveness / eligibility snapshot | `nodes` with `traceroute` compatibility exports | Managed-node liveness is fundamentally node state derived from ingestion. `traceroute.source_eligibility` may continue to re-export the canonical node helpers for compatibility.                                                             |
| Target selection and strategy rotation | `traceroute`                                    | These decide what generic automatic traceroute to run next. They are operational scheduling concerns, even when their output later feeds analytics.                                                                                           |
| Traceroute analytics                   | `traceroute_analytics`                          | Stats, success/failure breakdowns, top routers, by-source/by-target summaries, success-over-time, and daily `StatsSnapshot` collection are derived reporting products over `AutoTraceRoute`. They should not live in the core lifecycle app.  |
| Reach and coverage analytics           | `traceroute_analytics`                          | Feeder reach and constellation coverage are visualisation/reporting pivots over completed/failed traceroutes. They are useful, but not required for dispatch, completion, monitoring, or DX event handling.                                   |
| Neo4j graph export and queries         | `traceroute_analytics`                          | Neo4j is the graph/visualisation backend for heatmaps and node-link exploration. Export/query code should be decoupled from core traceroute lifecycle code.                                                                                   |
| Heatmap and topology API payloads      | `traceroute_analytics`                          | Heatmap and topology payloads are presentation-oriented analytics APIs. Public URLs can remain under `/api/traceroutes/` for compatibility, but implementation should live outside core traceroute.                                           |
| Observed-node traceroute links         | `nodes` route backed by `traceroute_analytics`  | The route belongs in the node-detail API surface, but the graph query implementation is traceroute analytics.                                                                                                                                 |
| WebSocket status notifications         | `traceroute`                                    | Status notifications are lifecycle events for manual, scheduled, monitoring, DX, baseline, and external traceroutes. They must not depend on analytics.                                                                                       |
| OpenAPI contract                       | API surface, currently `openapi.yaml`           | Public endpoint compatibility matters more than internal module layout. The refactor should preserve paths unless a separate migration plan deliberately changes them.                                                                        |


## Dependency Rules

The desired direction is a one-way dependency flow:

```text
packets / mesh_monitoring / dx_monitoring
        -> traceroute core service boundary
        -> optional lifecycle hooks
        -> traceroute_analytics
```

Core `traceroute` code should not import analytics modules for normal dispatch
or completion. If analytics needs to react to a completed traceroute, use an
explicit hook, task, or signal-like boundary so a Neo4j/reporting failure cannot
block mission-critical lifecycle work.

Operational apps may still query `AutoTraceRoute` where that is their domain
state, but new code should prefer core service helpers for creating,
completing, failing, or notifying traceroutes. That keeps producer-specific
policy in the producer app while preserving one lifecycle implementation.

## Refactor Notes

When splitting the code:

- Keep the `AutoTraceRoute` model and migrations in `traceroute`.
- Keep public API paths stable during the first refactor pass.
- Add compatibility wrappers for Celery task names if existing beat rows or
queued jobs reference old `traceroute.tasks.*` names.
- Move analytics implementation first, then clean up compatibility wrappers
only after deployed task/API compatibility is understood.
- Update this document when a functional area deliberately changes owner.

