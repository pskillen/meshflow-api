# Traceroute coverage

The coverage feature exposes "where can the mesh actually reach?" data derived
from auto-traceroute records. Rather than assuming circular RF reach, the
endpoints expose a per-(feeder, target) reliability fact table that the
frontend renders as per-node dots, H3-binned hexagons, and concave-hull
polygons.

Frontend ticket: [meshtastic-bot-ui#178](https://github.com/pskillen/meshtastic-bot-ui/issues/178).
Backend ticket: [meshflow-api#179](https://github.com/pskillen/meshflow-api/issues/179).

## The substrate

For every (feeder, target) pair seen in `AutoTraceRoute` over the requested
window, we count:

- `attempts`: rows with `status in {COMPLETED, FAILED}` (anything pending or
  sent is excluded — we don't yet know whether it'll succeed)
- `successes`: rows with `status = COMPLETED`

Targets without a known position (`NodeLatestStatus.latitude/longitude` both
non-null) are dropped; feeders without a known position (either
`ManagedNode.default_location_*` or the linked ObservedNode's latest status)
are dropped.

The shared helper is `Meshflow/traceroute/reach.py::compute_reach()`.

## Endpoints

### `GET /api/traceroutes/feeder-reach/`

Returns one row per (feeder, target) for the requested feeder. The frontend
fetches once per feeder and renders three layers off the same payload (dots,
H3 hexes, concave-hull polygon).

Required query params:

- `feeder_id` (integer, required): ManagedNode meshtastic node id.

Optional:

- `triggered_at_after`, `triggered_at_before` (ISO 8601 datetime).

Response shape: see `FeederReach` in `openapi.yaml`.

### `GET /api/traceroutes/constellation-coverage/`

Aggregates every feeder-target pair whose feeder belongs to the requested
constellation, then bins the targets by H3 cell on the server. The frontend
renders a single H3 hex layer.

Required query params:

- `constellation_id` (integer, required).

Optional:

- `triggered_at_after`, `triggered_at_before` (ISO 8601 datetime).
- `h3_resolution` (integer, default 6, clamped to [0, 15]).

H3 resolution 6 has ~3km edge length, which empirically matches Scotland's
mesh feeder spacing. Drop to 5 for sparser views, jump to 7 for very dense
clusters. See [H3 resolution table](https://h3geo.org/docs/core-library/restable).

Response shape: see `ConstellationCoverage` in `openapi.yaml`.

## Frontend smoothing

Both endpoints emit raw `attempts` and `successes`. The frontend smooths a
small-sample dot from misleading red to "honest unknown" by applying a
Bayesian Beta(α=1, β=1) prior:

```
smoothed_rate = (successes + 1) / (attempts + 2)
```

…and applies a `min_attempts` floor (configurable per page) below which a hex
or dot is rendered as "low confidence" rather than coloured by smoothed rate.

## Known gaps

- **No position-freshness filter**: targets are placed at the position from
  `NodeLatestStatus`, regardless of how stale that position is. Mobile nodes
  can put a hex/dot in the wrong place. Tracked separately.
- **Auth scoping**: like `feeder_ranges` (now removed) and `heatmap_edges`,
  the coverage endpoints only require authentication. `constellation_id` is
  a client-supplied filter rather than a membership-enforced scope.
- **Server vs client H3 versions**: the Python `h3` package and the
  frontend's `h3-js` package are kept on matching major versions (4.x both)
  so cell indexes encode identically.
