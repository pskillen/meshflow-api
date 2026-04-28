# Traceroute Heatmap

The heatmap visualizes aggregated traceroute traffic between nodes as arcs on a map. Data is stored in Neo4j and served via the `heatmap-edges` API. **Implementation** (schema, export, query): `traceroute_analytics` (`neo4j_service`, `views.heatmap_edges`). The URL remains `/api/traceroutes/heatmap-edges/` (wired from `traceroute.urls`).

## Neo4j Schema

- **MeshNode**: Node label with `node_id` (unique), `node_id_str`, `latitude`, `longitude`, `short_name`, `long_name`.
- **ROUTED_TO**: Relationship from one MeshNode to another. Properties:
  - `weight` (integer, one per traceroute hop – summed bidirectionally for the heatmap)
  - `triggered_at` (datetime)
  - `auto_tr_id`, `a_id`, `b_id` – merge key used for idempotent re-export
  - `snr` (float, optional – SNR at the receiving node for this hop)

Edges are directional in Neo4j, but the heatmap query aggregates bidirectionally (A→B and B→A are summed). The `snr` property is used by the node-links API for per-node traceroute link visualization.

## Data Flow

1. When an `AutoTraceRoute` completes, `push_traceroute_to_neo4j` calls `add_traceroute_edges`, which builds two full chains of `{node_id, snr}` entries and emits consecutive pairs.
2. **Meshtastic format:** `AutoTraceRoute.route` and `AutoTraceRoute.route_back` are **relay-only** lists. Neither the source (`AutoTraceRoute.source_node`, a `ManagedNode`) nor the target/responder (`AutoTraceRoute.target_node`, an `ObservedNode` matching the packet `from_node`) is stored in those lists. SNR is 1:1 with route indices (SNR at receiving node per firmware PR #4485). Firmware sometimes sends one extra trailing value in `snr_towards` / `snr_back`; that is the SNR at the responding endpoint for the final bookend hop and is pulled from the linked `raw_packet` when building the bookend edges.
3. `add_traceroute_edges` constructs:
   - Forward chain: `[source, *route, target]` → edges `source → route[0] → … → route[-1] → target`.
   - Return chain: `[target, *route_back, source]` → edges `target → route_back[0] → … → route_back[-1] → source`.
   - Direct traceroutes (both route lists empty) collapse to `(source, target)` and `(target, source)` when both endpoints have coordinates.
4. For each edge, both endpoints must have coordinates (from `ManagedNode.default_location_*` or `ObservedNode.latest_status`).
5. Nodes are upserted, and each edge is written with `MERGE (a)-[r:ROUTED_TO {auto_tr_id, a_id, b_id, triggered_at}]->(b)`. Re-exporting the same `AutoTraceRoute` therefore updates the existing relationship in place rather than duplicating it.

## Heatmap-Edges API

`GET /api/traceroutes/heatmap-edges/`

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `triggered_at_after` | ISO 8601 | Filter edges by `triggered_at >= value` |
| `constellation_id` | integer | Restrict to nodes in this constellation |
| `bbox` | string | `min_lat,min_lon,max_lat,max_lon` – viewport bounding box |

**Response:**

```json
{
  "edges": [
    {
      "from_node_id": 123,
      "to_node_id": 456,
      "from_lat": 55.86,
      "from_lng": -4.25,
      "to_lat": 55.87,
      "to_lng": -4.24,
      "weight": 5
    }
  ],
  "nodes": [
    {
      "node_id": 123,
      "node_id_str": "!a1b2c3d4",
      "lat": 55.86,
      "lng": -4.25,
      "short_name": "NodeA",
      "long_name": "Test Node A"
    }
  ],
  "meta": {
    "active_nodes_count": 3,
    "total_trace_routes_count": 10
  }
}
```

The query aggregates `ROUTED_TO` relationships bidirectionally (canonical direction `a.node_id < b.node_id`) and sums `weight`. Edges and nodes are filtered by `triggered_at_after`, `bbox`, and optionally `constellation_id`.

## Configuration

- **Neo4j**: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in settings.
- **Schema**: `ensure_schema()` creates the `MeshNode.node_id` unique constraint. Run on first use or via migration.
- **Bulk export**: Use `manage.py export_traceroutes_to_neo4j` to backfill Neo4j from existing completed traceroutes. The export is idempotent thanks to the `MERGE` semantics above, so re-runs safely pick up new synthetic edges without double-counting.
  - `--clear` first deletes every `ROUTED_TO` relationship (nodes are left untouched and re-upserted by the export). Useful when you want a guaranteed clean slate before a full re-export. Prompts for confirmation unless `--yes` is also given.
  - `--clear` is sync-only; combining it with `--async` raises `CommandError`.
