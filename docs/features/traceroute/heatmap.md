# Traceroute Heatmap

The heatmap visualizes aggregated traceroute traffic between nodes as arcs on a map. Data is stored in Neo4j and served via the `heatmap-edges` API.

## Neo4j Schema

- **MeshNode**: Node label with `node_id` (unique), `node_id_str`, `latitude`, `longitude`, `short_name`, `long_name`.
- **ROUTED_TO**: Relationship from one MeshNode to another. Properties: `weight` (integer, incremented per traceroute), `triggered_at` (datetime).

Edges are directional in Neo4j, but the heatmap query aggregates bidirectionally (A→B and B→A are summed).

## Data Flow

1. When an `AutoTraceRoute` completes, `push_traceroute_to_neo4j` extracts consecutive node pairs from `route` and `route_back`.
2. For each edge (from_id, to_id), both endpoints must have coordinates (from ManagedNode default_location or ObservedNode latest_status).
3. Nodes are upserted; `ROUTED_TO` relationships are created with `weight: 1` and `triggered_at`.

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
- **Bulk export**: Use `manage.py export_traceroutes_to_neo4j` to backfill Neo4j from existing completed traceroutes.
