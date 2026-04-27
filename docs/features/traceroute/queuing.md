# Traceroute Dispatch Queuing

This document describes how automatic and mesh-monitoring traceroute requests are queued and dispatched by the API.
It is aimed at developers and operators who need to reason about scheduling, pacing, retries, and observability.

## Goals

Traceroutes are paced by `meshflow-api`, not by the bot fleet. Bots continue to receive the existing single-command WebSocket payload:

```json
{
  "type": "node_command",
  "command": {
    "type": "traceroute",
    "target": 123456789
  }
}
```

This keeps bots simple and backwards-compatible while giving the API one durable place to handle fairness, queue depth, stale work, and dispatch errors.

## Queue Model

`AutoTraceRoute` rows are the durable queue. A queued traceroute is an `AutoTraceRoute` with:

- `status="pending"`: row exists but no command has been sent to the source bot yet.
- `earliest_send_at`: earliest time the dispatcher may attempt to send the command.
- `dispatch_attempts`: number of failed channel-layer delivery attempts.
- `dispatch_error`: most recent delivery or dispatch error, truncated by the model field size.
- `dispatched_at`: time the command was successfully delivered to the Channels group.

When dispatch succeeds, the dispatcher moves the row to `status="sent"` and sets `dispatched_at`.
The row later moves to `completed` when a matching traceroute response is ingested, or `failed` when stale timeout processing determines that no response arrived in time.

The queue is indexed on `(status, earliest_send_at)` so the dispatcher can find due pending rows efficiently.

## Producers

The queue has multiple producers. They all create `pending` rows and leave WebSocket delivery to `dispatch_pending_traceroutes`.

`schedule_traceroutes` is the automatic exploration scheduler. It picks one eligible source in LRU order, rotates through target strategies, creates one pending `AutoTraceRoute`, and returns. It no longer sends directly to Channels.

Mesh monitoring creates one pending `AutoTraceRoute` per selected monitoring source when a watched node enters verification. The old `send_monitoring_traceroute_command` task remains as a legacy hook, but it now delegates to the shared dispatcher instead of sending one specific row directly.

First-seen observed nodes enqueue at most one pending `AutoTraceRoute` per target with `trigger_type` **New node baseline** (integer 6). This uses the same dispatcher and per-source pacing as other producers; it is not part of DX Monitoring logic.

Manual HTTP triggers are the exception: they still send immediately from the request path. They set `dispatched_at` when the immediate Channels send succeeds so downstream stale timeout and observability stay consistent with queued work.

## Dispatch Task

`dispatch_pending_traceroutes` is a Celery task seeded by migration to run every 15 seconds. Each invocation repeatedly calls `try_dispatch_one()` until one of these happens:

- there is no due pending work,
- all scanned due work is blocked by per-source cooldown,
- the task has processed its internal safety loop limit.

`try_dispatch_one()` scans rows where:

```python
status == AutoTraceRoute.STATUS_PENDING
earliest_send_at <= timezone.now()
```

Rows are ordered by `earliest_send_at`, then `id`.

For each candidate, the dispatcher opens a short transaction, locks the row with `select_for_update()`, re-checks that it is still pending and due, and then checks whether that source is currently inside its dispatch cooldown. If the row is sendable, the dispatcher sends the WebSocket command and marks the row `sent`.

The Channels target group is based on the managed source node's mesh node id:

```python
f"node_{tr.source_node.node_id}"
```

The command target is the observed target node's mesh node id:

```python
{"type": "traceroute", "target": tr.target_node.node_id}
```

## Per-Source Pacing

Pacing is enforced per `ManagedNode` source. The dispatcher looks at the most recent non-null `dispatched_at` for the source and refuses to send another command until the interval has passed.

The default interval comes from `MONITORING_TRIGGER_MIN_INTERVAL_SEC` and is currently 30 seconds. Operators can override it with:

- `TRACEROUTE_DISPATCH_INTERVAL_SEC`

This cooldown applies across automatic scheduler rows, mesh-monitoring rows, and any future producer that uses the same pending queue.

The dispatcher scans beyond rows that are blocked by cooldown, so one busy source should not prevent another source's due row from being sent in the same dispatcher tick.

## Queue Bounds

New automatic and mesh-monitoring producers call `pending_count_for_source()` before creating work. If a source already has at least `TRACEROUTE_MAX_PENDING_PER_SOURCE` pending rows, the producer skips creating another row for that source and logs the skip.

The default cap is 20 pending rows per source. Operators can override it with:

- `TRACEROUTE_MAX_PENDING_PER_SOURCE`

Dispatcher scans are also bounded:

- `TRACEROUTE_DISPATCH_CANDIDATE_BATCH`: number of due row ids fetched per page, default 200.
- `TRACEROUTE_DISPATCH_MAX_SCAN`: maximum due rows scanned in one `try_dispatch_one()` call, default 10000.

These limits protect the dispatcher from spending unbounded time in one task run if the queue is large or many rows are blocked by cooldown.

## Failure And Retry Semantics

Dispatch failure means the command could not be handed to the Channels layer. In that case:

- the row stays `pending`,
- `dispatch_attempts` is incremented,
- `dispatch_error` stores the latest exception message,
- a later dispatcher run may retry the same row.

The dispatcher only marks a row `sent` after `group_send` returns successfully.

Channels `group_send` does not guarantee that a bot is currently connected or that the radio command ultimately succeeds. It only means the API handed the command to the channel layer. The existing traceroute response ingestion and stale timeout tasks still determine final `completed` or `failed` state.

## Mesh Monitoring Side Effects

For `trigger_type=NODE_WATCH`, successful dispatch also updates `NodePresence`:

- `last_tr_sent` is set to the dispatch time,
- `tr_sent_count` is incremented.

This preserves the mesh-monitoring verification counters while routing actual delivery through the shared queue.

If no monitoring sources are available, mesh monitoring does not create queue rows and instead updates `NodePresence.last_zero_sources_at`.

## Stale Timeout Handling

`mark_stale_traceroutes_failed` handles queued and sent rows differently.

For pending rows, timeout is based on `earliest_send_at`, not `triggered_at`. This prevents queued work from failing merely because it waited behind source pacing.

For sent rows, timeout is based on `dispatched_at` when available. Legacy sent rows without `dispatched_at` fall back to `triggered_at`.

The timeout window is controlled by:

- `FAILED_TR_TIMEOUT_SECONDS`, default 180 seconds.

When a row is marked stale, it moves to `status="failed"`, gets `completed_at`, and records an error message such as `Timed out after 180s`.

## Concurrency Notes

The dispatcher is safe to run concurrently because each candidate row is locked inside a database transaction before it is sent. The row is re-read under lock with `status="pending"` and `earliest_send_at <= now`, so a second worker that reaches the same row after the first worker has marked it `sent` will not send it again.

The per-source cooldown is checked after the row lock is acquired and before sending. This means concurrent workers may scan the same source, but only rows that still pass the locked pending/due check and the source cooldown check are dispatched.

## Operational Checks

Useful queue inspections from Django shell:

```python
from django.db.models import Count
from traceroute.models import AutoTraceRoute

AutoTraceRoute.objects.filter(status="pending").count()

AutoTraceRoute.objects.filter(status="pending").values("source_node").annotate(count=Count("id")).order_by("-count")[:20]

AutoTraceRoute.objects.filter(status="pending", dispatch_error__isnull=False).order_by("-triggered_at")[:20]
```

Useful fields in admin/API responses:

- `status`
- `triggered_at`
- `earliest_send_at`
- `dispatched_at`
- `dispatch_attempts`
- `dispatch_error`
- `error_message`

For normal operation, expect `pending` rows to be short lived unless a source has accumulated more requests than the configured per-source interval can drain.
