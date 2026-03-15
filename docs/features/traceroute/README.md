# Traceroute Feature

The traceroute feature tracks path discovery between Meshtastic nodes on the mesh network. It records source-to-target routes (and return paths), stores them in Django, exports them to Neo4j for graph analysis, and exposes aggregated data for heatmap visualization in the UI.

## Overview

- **AutoTraceRoute**: Django model recording each traceroute request (manual or scheduled) and its result.
- **Triggering**: Manual (user) or automatic (Celery scheduler every 2h).
- **Command delivery**: WebSocket (`NodeConsumer`) sends traceroute commands to connected bots (meshtastic-bot).
- **Completion**: Packet receiver matches incoming `TraceroutePacket` to `AutoTraceRoute` (same source/target within configurable window). If no match exists (e.g. cross-env: prod triggered, pre-prod received), creates an `AutoTraceRoute` with `trigger_type="external"`. Updates status and pushes to Neo4j.
- **Heatmap**: Neo4j stores edges; `heatmap-edges` API returns aggregated edges/nodes for map visualization.

## Data Model

| Field | Description |
|-------|-------------|
| `source_node` | ManagedNode that sends the traceroute |
| `target_node` | ObservedNode (destination) |
| `trigger_type` | `auto`, `user`, or `external` |
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
| `/api/traceroutes/trigger/` | POST | Manual trigger (admin/editor, requires `managed_node_id`, optional `target_node_id`) |
| `/api/traceroutes/can_trigger/` | GET | Whether current user can trigger |
| `/api/traceroutes/heatmap-edges/` | GET | Aggregated edges/nodes for heatmap (Neo4j) |

## Cross-Environment and Late Responses

When a node feeds data to multiple API instances (e.g. prod and pre-prod), a TR initiated by prod may have its response ingested by pre-prod. Pre-prod has no prior `AutoTraceRoute`, so the receiver creates one with `trigger_type="external"`. The only missing data is `triggered_at` (approximated as receive time).

Late responses: if a TR was marked `failed` (timeout) but the response arrives later, the receiver finds the failed record within the window and updates it to `completed`.

## Related Documentation

- [Flow](flow.md) – End-to-end lifecycle from trigger to completion
- [Heatmap](heatmap.md) – Neo4j schema, heatmap-edges API, visualization
