# Traceroute Coverage

The coverage feature answers a single operator question: **"where can the mesh
actually reach right now?"** It pivots existing `AutoTraceRoute` records
(both successes and failures) into a per-(feeder, target) reliability fact
table, then exposes that data through two read-only endpoints. The frontend
renders the same data four different ways depending on the question being
asked.

- **Frontend ticket:** [meshtastic-bot-ui#178](https://github.com/pskillen/meshtastic-bot-ui/issues/178)
- **Backend ticket:** [meshflow-api#179](https://github.com/pskillen/meshflow-api/issues/179)
- **Companion docs:** [Heatmap](heatmap.md) (related but distinct: aggregated
  edge weights from completed multi-hop paths).

---

## Why this exists (and what we tried first)

The original ticket [meshtastic-bot-ui#169](https://github.com/pskillen/meshtastic-bot-ui/issues/169)
shipped one circle per feeder, sized to a chosen percentile (`p50` / `p90` /
`p95` / `max`) of the geographic distance to its **successful** TR targets.
Operators rejected that design for two unrelated reasons:

1. **The metric inverted intuition.** A "p95 range" reads as "95% chance of
   success at this radius", but distance-percentile-of-successes produces
   *larger* circles for *higher* percentiles. No relabelling untangled that.
2. **Circles don't fit non-isotropic geography.** Our central-belt deployment
   hugs the M8 corridor with hills, lochs, and uneven node density. A single
   radius simultaneously oversold reach across the Campsies and undersold
   reach along the corridor.

The redesign deliberately:

- Treats reliability (`successes / attempts`) as a function of geographic
  area, not radius from a feeder.
- Includes failed traceroutes in the denominator so the metric is honest
  rather than survival-biased.
- Renders coverage as data-shaped polygons / hexes / dots instead of
  isotropic circles.
- Smooths small-sample bins so a single failure doesn't paint a hex red.

The parked PRs ([meshtastic-bot-ui#176](https://github.com/pskillen/meshtastic-bot-ui/pull/176)
and [meshflow-api#177](https://github.com/pskillen/meshflow-api/pull/177))
were rebased onto the redesign rather than thrown away.

---

## Design goals

| Goal | How we hit it |
|------|---------------|
| **Honest metric** | `attempts` includes both `COMPLETED` and `FAILED` traceroutes. We don't quietly drop failures. |
| **No isotropic assumptions** | Three rendering options (dots, H3 hex, concave hull). None of them is a circle. |
| **Stable in small samples** | Bayesian Beta(α=1, β=1) smoothing on the client. Per-page `min_attempts` floor. |
| **One source of truth** | Both endpoints share `compute_reach()`. Adding a third pivot is a few lines. |
| **Cheap-ish to render** | Per-feeder endpoint emits per-target rows; the frontend renders three layers off one fetch. Constellation-wide pre-bins server-side. |
| **Deep-linkable** | UI accepts `?feeder=<node_id>` so node-detail pages and infrastructure cards can hand off context. |
| **Reuses existing data** | Pure read pivot over `AutoTraceRoute`. No new ingestion path, no new background jobs. |

Non-goals (explicitly out of scope for this iteration):

- Resolving how nodes belonging to multiple constellations should aggregate.
  Current behaviour is "include rows whose feeder is in the constellation";
  overlap semantics are tracked separately.
- A constellation-wide concave hull (would be misleading at that scale).
- Time-of-day playback / animation.
- Replacing the existing [`/api/traceroutes/heatmap-edges/`](heatmap.md)
  Neo4j-backed heatmap (complementary, not a substitute — that one shows
  *paths*, this one shows *reliability surface*).
- Auth-scoping `constellation_id` to membership (see Known gaps below).

---

## The substrate: `compute_reach()`

For every (feeder, target) pair seen in `AutoTraceRoute` over the requested
window, we count:

- `attempts`: rows with `status in {COMPLETED, FAILED}` (anything still
  `PENDING` or `SENT` is excluded — we don't yet know whether they'll
  succeed).
- `successes`: rows with `status = COMPLETED`.

Targets without a known position (`NodeLatestStatus.latitude` /
`longitude` both non-null) are dropped. Feeders without a known position
(either `ManagedNode.default_location_latitude` / `longitude`, or — failing
that — the linked `ObservedNode.latest_status`) are also dropped.

Implementation:

- **`Meshflow/traceroute_analytics/reach.py::compute_reach()`** — single Django ORM
  pass: filter `AutoTraceRoute` → group by `(source_node_id, target_node_id)`
  → annotate `attempts = Count('id')` and
  `successes = Count('id', filter=Q(status=COMPLETED))`.
- **`Meshflow/traceroute_analytics/reach.py::ReachRow`** — frozen dataclass row type
  carrying both the counts and pre-resolved feeder + target metadata
  (display names, lat/lng, hex node id) so callers don't re-query.
- Bulk position lookups (one query for feeders, one for targets) are
  factored into `_bulk_feeder_positions()` and
  `_bulk_target_positions_by_node_id()`.

`compute_reach()` accepts mutually-compatible filters:

- `triggered_at_after`, `triggered_at_before` (time window)
- `feeder_id` (single ManagedNode meshtastic node id)
- `constellation_id` (filter to feeders in this constellation; targets are
  *not* filtered, by design — we want to see how far into other regions a
  constellation's feeders reach)
- `target_strategy_tokens` (optional list of strings, e.g. ``intra_zone``,
  ``dx_across``, ``legacy``): when provided, only traceroutes whose
  ``AutoTraceRoute.target_strategy`` matches one of the tokens are counted.
  ``legacy`` matches null or explicit legacy strategy (same semantics as the
  traceroute list ``target_strategy`` query param).

Both view functions are thin wrappers over this helper.

---

## Endpoints

Both endpoints require authentication (`IsAuthenticated`). Neither performs
constellation-membership scoping yet — see Known gaps.

### `GET /api/traceroutes/feeder-reach/`

Per-target rows for a single feeder. The frontend fetches once and renders
three layers off the same payload (dots, H3 hex, concave-hull polygon).

Implemented in **`Meshflow/traceroute_analytics/views.py::feeder_reach()`**.

**Query parameters**

| Name | Required | Type | Notes |
|------|----------|------|-------|
| `feeder_id` | yes | integer | Meshtastic node id of a `ManagedNode`. 400 if missing or non-integer; 404 if not found. |
| `triggered_at_after` | no | ISO 8601 datetime | Start of window (inclusive). |
| `triggered_at_before` | no | ISO 8601 datetime | End of window (inclusive). |
| `target_strategy` | no | comma-separated strings | Same tokens as the traceroute list filter (`intra_zone`, `dx_across`, `dx_same_side`, `legacy`). When omitted, all strategies count. |

**Response shape** (full schema: `FeederReach` in `openapi.yaml`)

```json
{
  "feeder": {
    "managed_node_id": "uuid-string",
    "node_id": 1127903080,
    "node_id_str": "!4339d0a8",
    "short_name": "HILL",
    "long_name": "Hilltop",
    "lat": 55.86,
    "lng": -4.25
  },
  "targets": [
    {
      "node_id": 100,
      "node_id_str": "!00000064",
      "short_name": "TGT",
      "long_name": "Target",
      "lat": 55.87,
      "lng": -4.26,
      "attempts": 5,
      "successes": 4
    }
  ],
  "meta": {
    "window": { "start": "2026-04-12T00:00:00Z", "end": null }
  }
}
```

When the feeder exists but has no traceroutes in the window, `targets` is an
empty array and `feeder.lat` / `feeder.lng` fall back to
`ManagedNode.default_location_*` so the map can still centre on it.

### `GET /api/traceroutes/constellation-coverage/`

Server-side H3-binned reach for an entire constellation. The frontend
renders a single `H3HexagonLayer` over these cells.

Implemented in **`Meshflow/traceroute_analytics/views.py::constellation_coverage()`**.

**Query parameters**

| Name | Required | Type | Notes |
|------|----------|------|-------|
| `constellation_id` | yes | integer | 400 if missing or non-integer. |
| `triggered_at_after` | no | ISO 8601 datetime | |
| `triggered_at_before` | no | ISO 8601 datetime | |
| `h3_resolution` | no | integer | Default 6. Clamped to `[0, 15]`. |
| `target_strategy` | no | comma-separated strings | Restrict rows to these selection strategies before binning (same semantics as `feeder-reach`). |
| `include_targets` | no | boolean-ish | When `1`, `true`, `yes`, or `on`, the response also includes `targets` (per-target aggregates across all feeders) and `feeders` (all managed nodes in the constellation with a map position). Omit or false for the original hex-only payload. |

**Aggregation**

For each `ReachRow` whose feeder belongs to the constellation:

1. Bin the **target** position into an H3 cell at `h3_resolution`
   (`h3.latlng_to_cell(target_lat, target_lng, h3_resolution)`).
2. Sum `attempts` and `successes` into that cell.
3. Track distinct contributing feeders and targets per cell.
4. Emit one row per cell with the cell centre lat/lng for convenience.

**Why H3?** It's a hierarchical hexagonal grid that gives uniform-area cells
across latitudes (a property neither lat/lng squares nor the slippy-map
quadtree have). Hex aggregation hides individual node identities while
preserving spatial structure.

**Picking a resolution**

| Res | ~edge length | When to use |
|-----|-------------|-------------|
| 5 | ~9 km | Very sparse coverage (rural tail) |
| 6 | ~3 km | Default — matches Scotland's mesh feeder spacing |
| 7 | ~1.2 km | Dense urban clusters where you want to see street-level structure |

See the [H3 resolution table](https://h3geo.org/docs/core-library/restable)
for full numbers.

**Response shape** (full schema: `ConstellationCoverage` in `openapi.yaml`)

```json
{
  "constellation_id": 1,
  "h3_resolution": 6,
  "hexes": [
    {
      "h3_index": "8616a4a17ffffff",
      "centre_lat": 55.86,
      "centre_lng": -4.25,
      "attempts": 27,
      "successes": 21,
      "contributing_feeders": 3,
      "contributing_targets": 8
    }
  ],
  "meta": {
    "window": { "start": "2026-04-12T00:00:00Z", "end": null }
  }
}
```

When `include_targets=1`, two extra top-level arrays are present:

- **`targets`**: one object per distinct target node reached in the window,
  with summed `attempts` / `successes` across every feeder in the constellation
  and `contributing_feeders` (distinct feeder count that attempted that target).
- **`feeders`**: one object per `ManagedNode` in the constellation that has a
  resolvable position (`default_location_*` or linked `ObservedNode.latest_status`),
  regardless of whether it appears in the window's traceroute rows — so the map
  can always show infrastructure.

---

## Frontend rendering

The UI is split across two pages, both at `/traceroutes/map/coverage*`. The
backend doesn't care, but documenting the rendering choices here helps when
a metric question comes back. Source files live in
[`meshtastic-bot-ui`](https://github.com/pskillen/meshtastic-bot-ui).

### Per-feeder page → `FeederCoveragePage`

- `useFeederReach(feederId, window)` (5-minute cache-key rounding) fetches
  one `FeederReach` payload.
- `FeederCoverageMap` renders three independently togglable layers off the
  same `targets` array:
  - **Dots** (`ScatterplotLayer`, default ON). One dot per target, coloured
    by smoothed reliability, sized by attempt count, with a low-confidence
    floor.
  - **Hex** (`H3HexagonLayer`). Client-side binning with `h3-js`
    (`latLngToCell`) at resolution 6, smoothed rate per hex.
  - **Polygon** (`PolygonLayer`). Concave hull
    (`turf.concave({ maxEdge: 2, units: 'kilometers' })`) over targets with
    `successes >= 1`, with a fallback to a buffered point if there are
    fewer than 3 reachable targets.
- Toolbar: feeder picker, time window (24h / 7d / 30d), min-attempts input,
  layer pills.
- Deep-link via `?feeder=<node_id>`. Any link from `NodeDetails` (managed
  nodes only) or the Mesh Infrastructure cards / no-location table sets
  this param.

### Constellation page → `ConstellationCoveragePage`

- `useConstellationCoverage(constellationId, window, h3Resolution)` fetches
  one `ConstellationCoverage` payload (optionally with `include_targets=1` for
  per-target dots and managed-node markers).
- `ConstellationCoverageMap` renders a single `H3HexagonLayer` over the
  server-binned hexes, and when included, dots plus feeder icon markers.
- Toolbar: constellation picker, time window, H3 resolution control,
  min-attempts input.
- Hex-click popup shows `successes / attempts`, smoothed rate,
  `contributing_feeders`, `contributing_targets`.

### Smoothing and the min-attempts floor

The endpoints emit raw counts. The frontend applies a Bayesian
Beta(α=1, β=1) prior so a 0/1 hex doesn't paint full red:

```text
smoothed_rate = (successes + 1) / (attempts + 2)
```

A `min_attempts` floor (default 3, configurable per page) hides bins below
that count from the colour scale entirely so they read as "low confidence"
rather than mid-amber.

The colour ramp is red (0%) → amber (~70%) → green (~90%+). It's
intentionally non-linear: the steepest discrimination is in the
"unreliable" band where operators most want to act.

### Deck.gl + Mapbox plumbing

Same pattern as the existing heatmap page: a `react-map-gl` `<Map>` with a
deck.gl `MapboxOverlay` (`interleaved: false`) for layer rendering. The
shared rendering bug that affects all overlay maps when the surrounding
React tree manipulates the map programmatically
([meshtastic-bot-ui#150](https://github.com/pskillen/meshtastic-bot-ui/issues/150))
applies here too.

### Side-quest: dashboard concave hulls

While we were adding `turf.concave` for the polygon layer, the existing
`buildBoundaryFromPoints()` in `src/components/nodes/map-utils.ts` was
updated to prefer `turf.concave({ maxEdge: 2 km })` with convex-hull
fallback. `ConstellationsMap` and `NodesAndConstellationsMap` pick this up
automatically, replacing the previous "huge convex envelope across the
central belt" with hull shapes that hug clusters.

---

## Known gaps

- **No position-freshness filter.** Targets are placed at whatever
  `NodeLatestStatus` currently says. Mobile or recently-relocated nodes
  can put a hex/dot in the wrong place. We accept this trade-off for now
  because the alternative (scoring positions by recency) adds complexity
  without an obvious operator benefit. Tracked separately.
- **Auth scoping.** Like `feeder_ranges` (now removed) and
  `heatmap_edges`, the coverage endpoints only require authentication.
  `constellation_id` is a client-supplied filter rather than a
  membership-enforced scope. Anyone authenticated can read coverage for
  any constellation. Aligning these endpoints with constellation
  membership is tracked alongside the same change for `heatmap_edges`.
- **H3 version coupling.** The Python `h3` package and the frontend's
  `h3-js` package are kept on matching major versions (4.x both) so cell
  indexes encode identically. Bumping one without the other will silently
  break hex-click popups.
- **Constellation overlap.** A target reached by feeders in two
  constellations contributes to both constellations' coverage maps. This
  is the intended behaviour for now (operators want a feeder's reach
  visible in every constellation it serves), but the formal semantics for
  overlapping/adjacent constellations are still TBD.
- **Window endpoints not snapped.** `triggered_at_after` /
  `triggered_at_before` are passed through verbatim. The frontend rounds
  to the nearest five minutes for cache stability; the backend does not.

---

## File map

Backend (this repo):

- `Meshflow/traceroute_analytics/reach.py` — `compute_reach()`, `ReachRow`
- `Meshflow/traceroute_analytics/views.py` — `feeder_reach()`,
  `constellation_coverage()`, `_parse_window()`
- `Meshflow/traceroute/urls.py` — `feeder-reach/`,
  `constellation-coverage/`
- `Meshflow/traceroute_analytics/tests/test_reach.py` — unit tests for the helper
- `Meshflow/traceroute_analytics/tests/test_views.py` — `TestFeederReach`,
  `TestConstellationCoverage`
- `openapi.yaml` — `FeederReach`, `FeederReachFeeder`,
  `FeederReachTarget`, `ConstellationCoverage`,
  `ConstellationCoverageHex`, `CoverageWindow`

Frontend (`meshtastic-bot-ui`):

- `src/hooks/api/useFeederReach.ts`
- `src/hooks/api/useConstellationCoverage.ts`
- `src/pages/traceroutes/FeederCoveragePage.tsx`
- `src/pages/traceroutes/ConstellationCoveragePage.tsx`
- `src/components/traceroutes/FeederCoverageMap.tsx`
- `src/components/traceroutes/ConstellationCoverageMap.tsx`
- `src/components/nodes/map-utils.ts` — `boundaryPolygonFromPoints` (the
  dashboard concave-hull side-quest)
