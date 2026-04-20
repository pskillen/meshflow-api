# RF propagation renders

Owners of observed nodes can request a predicted RF coverage map for their
hardware, rendered as a Leaflet PNG overlay. This document covers how the
pipeline fits together in production.

## Architecture

```
UI                 api (Django)            celery-rf-worker         rf-propagation (Site Planner)
 │                      │                         │                           │
 │ POST /rf-propagation/recompute ─────────────── │                           │
 │                      │── enqueue (rf_renders)─►│                           │
 │ 201 { status: pending, … }                    │ POST /predict ────────────►│
 │                      │                         │ GET /status (polling)◄────│
 │                      │                         │ GET /result (GeoTIFF)◄────│
 │                      │                         │ tiff → png → rf_assets    │
 │                      │                         │ update render row         │
 │ GET /rf-propagation/ (polling)                 │                           │
 │ 200 { status: ready, asset_url, bounds }       │                           │
 │ GET {asset_url} (public PNG) ─────────────────►│                           │
```

Three containers collaborate on every render:

- **api** accepts the request and holds the `NodeRfProfile` /
  `NodeRfPropagationRender` rows. See `nodes/views.py::rf_propagation_recompute`.
- **celery-rf-worker** consumes the dedicated `rf_renders` queue and drives
  one render to completion. See `rf_propagation/tasks.py`.
- **rf-propagation** (image `ghcr.io/pskillen/meshflow-rf-propagation`) is
  an external FastAPI service that wraps SPLAT! and returns a GeoTIFF.

## Engine dependency

The engine is pulled (not built) from GHCR; the source lives in the
`meshflow-rf-propagation` repository. Local stacks default to the
`latest-dev` tag; Portainer stacks pin an explicit `RF_PROPAGATION_TAG`
in `.env.portainer.*`.

Smoke-test the engine without the UI:

```bash
# local docker compose
docker compose exec api curl -sf http://rf-propagation:8080/docs >/dev/null && echo ok

# portainer stack (service is named "site-planner" there)
docker compose exec api curl -sf http://site-planner:8080/docs >/dev/null && echo ok
```

## Redis layout

Redis is shared across services with logical database partitioning — see
[docs/REDIS.md](../../REDIS.md). In short: Channels on DB 0, Celery broker
on DB 1, Django cache on DB 2, and the Site Planner engine on **DB 3**
for its own task state.

## Hashing and cache strategy

`rf_propagation.hashing.compute_input_hash` produces a SHA256 digest over:

- The rounded RF profile fields (lat/lng to 6 dp, metres to 2 dp, dB to
  1 dp, frequency to 3 dp).
- `antenna_pattern`, azimuth, beamwidth (captured even though Site Planner
  currently ignores them — future engines may use them).
- `render_version` from `settings.RF_PROPAGATION_RENDER_VERSION`.
- The target radius (so changing `RF_PROPAGATION_DEFAULT_RADIUS_M`
  invalidates existing renders).

The hash doubles as the on-disk filename (`{hash}.png`). Two nodes with
identical RF profiles therefore share a PNG.

### Single-inflight dedup

`rf_propagation_recompute` will:

1. Reuse a `ready` render with a matching hash (no new row, no engine
   call) whose asset still exists on disk.
2. Otherwise return any `pending`/`running` row that already exists for
   the same node without enqueueing another task.
3. Otherwise create a fresh `pending` row and `.delay()` the render task.

### Bumping `render_version`

Any time the render recipe changes (colormap, colour scale, default
radius, radio climate, post-processing) bump
`RF_PROPAGATION_RENDER_VERSION` so the next request per node produces a
fresh cache entry instead of reusing a stale PNG. The old PNG files are
cleaned up lazily by the retention rule below.

## Retention

On every successful render, the task keeps the **3 most recent** ready
renders per node (configurable via `RF_PROPAGATION_READY_RETENTION`) and
deletes any older ready rows plus their PNG files. `failed` rows older
than 7 days are also pruned per node.

## Environment variables

| Variable | Default | Where used | Notes |
| --- | --- | --- | --- |
| `RF_PROPAGATION_ENGINE_URL` | _(empty)_ | worker | Internal URL of the engine, e.g. `http://rf-propagation:8080`. Required for real renders. |
| `RF_PROPAGATION_ASSET_DIR` | `/var/meshflow/generated-assets/rf-propagation` | api + worker | Mounted from the `rf_assets` named volume; must be shared between `api` and `celery-rf-worker`. |
| `RF_PROPAGATION_IMAGE_TAG` | `latest-dev` | compose | Tag for the engine image. |
| `RF_PROPAGATION_RENDER_VERSION` | `1` | api + worker | Bump to invalidate all cached renders. |
| `RF_PROPAGATION_DEFAULT_RADIUS_M` | `20000` | api + worker | Radius of the predicted coverage bbox in metres. |
| `RF_PROPAGATION_POLL_MAX_SECONDS` | `300` | worker | Cap on cumulative polling before the render is marked failed. |
| `RF_PROPAGATION_READY_RETENTION` | `3` | worker | Number of `ready` renders kept per node. |

## Known limitations

- **Directional antennas**: Site Planner's current model is omni-only.
  The UI still collects azimuth/beamwidth so we can render directional
  predictions once the engine supports them; for now we log a WARN and
  render an omni coverage map. Azimuth/beamwidth are still folded into
  the hash, so an operator toggling between omni and directional gets a
  fresh cache entry.
- **SRTM coverage**: The default engine image ships UK SRTM tiles.
  Requests for nodes outside the shipped coverage fail with an
  `engine task … reported status=failed` and are surfaced on the row's
  `error_message`.
- **Pillow first, tifffile fallback**: some non-baseline GeoTIFFs trip
  Pillow. The converter falls back to `tifffile`; adding `rasterio`
  later would only be necessary if we see unreadable variants in
  production.

## Operational runbook

- **Stuck render?** Check the row: `status`, `error_message`, and
  `completed_at`. A pending row with no matching celery log usually
  means the queue is unconsumed — check `celery-rf-worker` logs.
- **Force re-render**: bump `RF_PROPAGATION_RENDER_VERSION` or PATCH the
  profile to invalidate the hash.
- **Purge disk**: `RF_PROPAGATION_READY_RETENTION=0` will GC on the next
  render; otherwise `ls $RF_PROPAGATION_ASSET_DIR` and remove by hand.
- **Engine upgrade**: bump `RF_PROPAGATION_IMAGE_TAG` in the env file
  and redeploy only the `rf-propagation`/`site-planner` service.
