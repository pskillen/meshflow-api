# Traceroute Feature

The traceroute feature tracks path discovery between Meshtastic nodes on the mesh network. It records source-to-target routes (and return paths), stores them in Django, exports them to Neo4j for graph analysis, and exposes aggregated data for heatmap visualization in the UI.

## Overview

- **AutoTraceRoute**: Django model recording each traceroute request (manual or scheduled) and its result.
- **Triggering**: Manual (user) or automatic (Celery scheduler every 2h). **Mesh monitoring** (when enabled) adds verification traceroutes with `trigger_type=monitor`; see [Mesh monitoring](../mesh-monitoring/README.md).
- **Command delivery**: WebSocket (`NodeConsumer`) sends traceroute commands to connected bots (meshtastic-bot).
- **Completion**: Packet receiver matches incoming `TraceroutePacket` to `AutoTraceRoute` (same source/target within configurable window). If no match exists (e.g. cross-env: prod triggered, pre-prod received), creates an `AutoTraceRoute` with `trigger_type="external"`. Updates status and pushes to Neo4j.
- **Heatmap**: Neo4j stores edges; `heatmap-edges` API returns aggregated edges/nodes for map visualization.

## Data Model

| Field | Description |
|-------|-------------|
| `source_node` | ManagedNode that sends the traceroute |
| `target_node` | ObservedNode (destination) |
| `trigger_type` | `auto`, `user`, or `external`; **`monitor`** when mesh-monitoring verification is implemented |
| `triggered_by` | User (manual only) |
| `trigger_source` | e.g. `scheduler` (null for external) |
| `status` | `pending` → `sent` → `completed` or `failed` |
| `route` | JSON list of `{node_id, snr}` (forward path) |
| `route_back` | JSON list of `{node_id, snr}` (return path) |
| `raw_packet` | FK to TraceroutePacket |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/traceroutes/` | GET | List traceroutes (filter by managed_node, target_node, status, triggered_after, etc.) |
| `/api/traceroutes/<pk>/` | GET | Single traceroute detail |
| `/api/traceroutes/trigger/` | POST | Manual trigger (requires `managed_node_id`, optional `target_node_id`; user must be staff, owner of source node, or constellation admin/editor) |
| `/api/traceroutes/can_trigger/` | GET | Whether current user has at least one triggerable node |
| `/api/traceroutes/triggerable-nodes/` | GET | ManagedNodes the current user can trigger traceroutes from |
| `/api/traceroutes/heatmap-edges/` | GET | Aggregated edges/nodes for heatmap (Neo4j) |
| `/api/traceroutes/feeder-reach/` | GET | Per-target attempts/successes for one feeder (coverage map) |
| `/api/traceroutes/constellation-coverage/` | GET | Server-side H3-binned reach for one constellation (coverage map) |

## Permissions

| Role | Can trigger from |
|------|------------------|
| System admin (`is_staff`) | Any ManagedNode with `allow_auto_traceroute=True` |
| Constellation admin/editor | Nodes in constellations where user has admin/editor role |
| ManagedNode owner | Nodes they own (`ManagedNode.owner == user`) |
| All authenticated | View traceroute list, detail, heatmap |

## Cross-Environment and Late Responses

When a node feeds data to multiple API instances (e.g. prod and pre-prod), a TR initiated by prod may have its response ingested by pre-prod. Pre-prod has no prior `AutoTraceRoute`, so the receiver creates one with `trigger_type="external"`. The only missing data is `triggered_at` (approximated as receive time).

Late responses: if a TR was marked `failed` (timeout) but the response arrives later, the receiver finds the failed record within the window and updates it to `completed`.

**Direct path:** `route` and `route_back` may both be empty when the source and target are in direct RF range (no repeaters on the path). Inferred `external` completions can therefore have empty hop lists; that is still a successful traceroute, not a timeout.

## Code map (shared helpers)

Auto-scheduler and permission checks share one notion of a **live** source node (recent packet ingestion as observer). Canonical implementation: **`nodes.managed_node_liveness`** (`eligible_auto_traceroute_sources_queryset`, etc.). **`traceroute.source_eligibility`** re-exports the same API for existing imports.

**Target selection** for auto TR: `traceroute.target_selection.pick_traceroute_target` uses **`common.geo.haversine_km`** and **`nodes.positioning.managed_node_lat_lon`**.

**Manual trigger rate limit**: **`traceroute.trigger_intervals.MANUAL_TRIGGER_MIN_INTERVAL_SEC`**. Mesh monitoring (future Celery) can use **`MONITORING_TRIGGER_MIN_INTERVAL_SEC`** for a shorter default.

## Related Documentation

- [Permissions](permissions.md) – Canonical rules for who may view and trigger traceroutes
- [Flow](flow.md) – End-to-end lifecycle from trigger to completion
- [Heatmap](heatmap.md) – Neo4j schema, heatmap-edges API, visualization
- [Coverage](coverage.md) – Per-feeder and per-constellation reliability surface (dots, H3 hexes, concave-hull polygons)
- [Mesh monitoring](../mesh-monitoring/README.md) – watches, verification rounds, `pick_traceroute_target` exclusion for nodes under monitoring
