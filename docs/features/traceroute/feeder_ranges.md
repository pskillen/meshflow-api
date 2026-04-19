# Per-Feeder Success Range

For every ManagedNode ("feeder"), summarise the geographic distance to the
target ObservedNodes of its **successful** AutoTraceRoutes within a time
window. Surfaced as percentiles (`p50`, `p90`, `p95`, `max`) plus a
`sample_count`, and split into two partitions:

- **`direct`** — only TRs where both `route` and `route_back` are empty (RF
  reach, no relays). The same condition `add_traceroute_edges` uses for
  synthetic direct edges (see [`heatmap.md`](heatmap.md), point 3).
- **`any`** — every successful TR, including multi-hop completions.

In plain English: "this feeder reaches out to roughly here." Mountain-top
relays will sport huge circles; rural handhelds, small ones.

## Endpoint

`GET /api/traceroutes/feeder-ranges/`

### Query parameters

| Parameter             | Type       | Description                                                          |
| --------------------- | ---------- | -------------------------------------------------------------------- |
| `triggered_at_after`  | ISO 8601   | Window start (mirrors `heatmap-edges`).                              |
| `triggered_at_before` | ISO 8601   | Window end (optional).                                               |
| `constellation_id`    | integer    | Restrict feeders to this constellation.                              |
| `min_samples`         | integer    | Override the low-confidence floor (default `10`).                    |

### Response

```json
{
  "feeders": [
    {
      "managed_node_id": "12d3a456-...",
      "node_id": 305419896,
      "node_id_str": "!12345678",
      "short_name": "GLA-RT",
      "long_name": "Glasgow Roof",
      "lat": 55.86,
      "lng": -4.25,
      "direct": {
        "sample_count": 84,
        "p50_km": 4.2, "p90_km": 11.1, "p95_km": 14.3, "max_km": 22.7,
        "low_confidence": false
      },
      "any": {
        "sample_count": 312,
        "p50_km": 8.6, "p90_km": 26.4, "p95_km": 38.0, "max_km": 71.2,
        "low_confidence": false
      }
    }
  ],
  "meta": {
    "min_samples": 10,
    "window": {"start": "2026-04-12T00:00:00+00:00", "end": null}
  }
}
```

A feeder is included when it has a resolvable position and at least one
completed TR with a positioned target in the window. `direct` may have
`sample_count: 0` if the feeder never completed a relay-free TR; `any` is
always non-zero for included feeders.

## Implementation notes

- Pure aggregation, no Neo4j. Cheap to compute on the fly for sensible windows
  (24h–30d).
- Helpers reused: [`common/geo.py`](../../../Meshflow/common/geo.py)
  (`haversine_km`) and [`nodes/positioning.py`](../../../Meshflow/nodes/positioning.py)
  (feeder position resolution: `default_location_*` first, then
  `ObservedNode.latest_status`).
- Target position via `NodeLatestStatus` joined to `ObservedNode`.
- Feeder + target positions are bulk-fetched in two queries each, so the cost
  scales with row count, not feeder count.

## Caveats (surface in tooltips and docs)

- **Round-trip**: a successful TR means the request reached the target *and* a
  response came back. Range here is therefore the asymmetric link's *min*
  capacity, not its full reach.
- **Distribution is biased by what we attempt**: if we never try to reach far
  targets, we'll never observe far successes. `p95` is a *lower bound* on real
  range, not a ceiling.
- Terrain / antenna height heavily skew this — and that's the whole point.
  Don't try to "normalise it out."

## Sample-size floor

Below `min_samples` (default 10) successful TRs in window, the partition is
flagged `low_confidence: true`. The data is still returned so the UI can
choose to render it with a distinct (e.g. dashed/translucent) style or hide it
behind a toggle.
