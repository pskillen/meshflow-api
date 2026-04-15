# Traceroute Flow

End-to-end lifecycle of a traceroute from trigger to completion.

## Permissions

Who can trigger traceroutes and from which nodes:

| Role | Can trigger from |
|------|------------------|
| System admin (`is_staff`) | ManagedNodes with `allow_auto_traceroute=True` and recent ingestion as `PacketObservation.observer` |
| Constellation admin/editor | Same eligibility, in constellations where user has admin/editor role |
| ManagedNode owner | Same eligibility for nodes they own |
| All authenticated | View traceroute list, detail, heatmap |

The UI fetches `GET /api/traceroutes/triggerable-nodes/` to list sources that are both permitted and recently ingesting (same rule as the Celery scheduler: **`nodes.managed_node_liveness`**, exposed via **`traceroute.source_eligibility`** for traceroute code). The trigger view validates eligibility, `user_can_trigger_from_node(user, source_node)`, and rate limits before sending the command.

## 1. Trigger

**Manual**: User calls `POST /api/traceroutes/trigger/` with `managed_node_id` and optional `target_node_id`. Source must match the same eligibility as auto-schedule (recent ingestion window `SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS`). Requires permission as above. Rate limit: **`traceroute.trigger_intervals.MANUAL_TRIGGER_MIN_INTERVAL_SEC`** (default 60s) per source node.

**Automatic**: Celery task `schedule_traceroutes` runs periodically. Picks one random ManagedNode with `allow_auto_traceroute=True` **and** recent packet ingestion as `PacketObservation.observer` (within `SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS`, default 600s; see **`nodes.managed_node_liveness`**), uses **`pick_traceroute_target()`** to select a target (geography via **`common.geo.haversine_km`** and **`nodes.positioning.managed_node_lat_lon`**, prioritises periphery and less-recently-traced nodes), creates `AutoTraceRoute` with `trigger_type=auto`. **`pick_traceroute_target()`** excludes observed nodes that have **`mesh_monitoring.NodePresence`** with active verification or offline confirmed.

**Mesh monitoring**: Celery task **`mesh_monitoring.tasks.process_node_watch_presence`** (beat, default every 60s) creates `AutoTraceRoute` rows with `trigger_type=monitor` and `trigger_source=mesh_monitoring` for watched nodes that are silent past their effective threshold; commands use the same WebSocket path as above. See [mesh monitoring](../mesh-monitoring/README.md).

## 2. Command Delivery

The API (or Celery task) sends a command via Django Channels:

```python
channel_layer.group_send(
    f"node_{source_node.node_id}",
    {"type": "node_command", "command": {"type": "traceroute", "target": target_node.node_id}},
)
```

The **NodeConsumer** WebSocket (`ws/nodes/?api_key=...`) is subscribed to `node_{node_id}`. When a bot (meshtastic-bot) connects with a NodeAPIKey for that ManagedNode, it receives the command and forwards it to the Meshtastic device.

## 3. Device Execution

The Meshtastic device performs the traceroute on the mesh. The firmware enforces ~30s minimum between traceroutes per node.

## 4. Packet Ingestion

When the traceroute response is received, the bot reports it as a packet. The packet ingestion pipeline creates a `TraceroutePacket` and emits `traceroute_packet_received`.

## 5. Receiver: Match and Complete

`packets.receivers.on_traceroute_packet_received`:

1. Finds a matching `AutoTraceRoute` (same source, target, triggered within configurable window, status pending/sent/failed). Window: `STALE_TR_TIMEOUT_SECONDS` (default 180s). Includes `failed` so late responses can update a previously timed-out record.
2. If no match: creates an **external** `AutoTraceRoute` (cross-env or orphaned response). Use case: prod triggers a TR, but the response is ingested by pre-prod (shared node feeding both APIs). Pre-prod has no prior record, so it creates one with `trigger_type="external"`, `triggered_at=now()`. Target `ObservedNode` is created if missing.
3. Builds `route` and `route_back` from packet data (node_ids + SNR).
4. If route is empty: marks `STATUS_FAILED`, `error_message="Timed out"`.
5. If route has data: marks `STATUS_COMPLETED`, saves route/route_back, links `raw_packet`.
6. Broadcasts status via `notify_traceroute_status_changed()` to WebSocket clients.
7. Queues `push_traceroute_to_neo4j.delay(auto_tr.id)` for completed traceroutes.

## 6. Stale Timeout

Celery task `mark_stale_traceroutes_failed` runs every 60 seconds. Traceroutes still `pending` or `sent` after 180s (configurable via `FAILED_TR_TIMEOUT_SECONDS`) are marked `failed` with `error_message="Timed out after 180s"`. Each update is broadcast to WebSocket clients.

**Configuration**: `STALE_TR_TIMEOUT_SECONDS` (receiver match window, default 180s); `FAILED_TR_TIMEOUT_SECONDS` (stale task cutoff, default 180s).

## 7. Neo4j Export

`push_traceroute_to_neo4j` (Celery): For each completed `AutoTraceRoute`, extracts edges from `route` and `route_back`, upserts `MeshNode` vertices, creates `ROUTED_TO` relationships with `weight` and `triggered_at`. Only edges where both endpoints have coordinates are stored.

Bulk export: `export_traceroutes_to_neo4j` task or `manage.py export_traceroutes_to_neo4j` (with `--async` to queue as Celery task).
