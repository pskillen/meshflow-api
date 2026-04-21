# RF propagation renders

Owners of observed nodes can request a predicted RF coverage map for their
hardware, rendered as a Leaflet PNG overlay. This document covers how the
pipeline fits together in production.

## Architecture

```mermaid
sequenceDiagram
    participant UI
    participant API as api (Django)
    participant Q as Redis (DB 1)<br/>rf_renders queue
    participant W as celery-rf-worker
    participant E as rf-propagation<br/>(Site Planner)
    participant FS as rf_assets volume

    UI->>API: POST /rf-propagation/recompute/
    API->>API: hash profile &amp; dedup (cache / in-flight)
    API->>Q: enqueue render task (rf_renders)
    API-->>UI: 201 { status: pending, input_hash }

    W->>Q: BRPOP rf_renders
    W->>E: POST /predict (lat, lon, frequency_mhz, …)
    E-->>W: 200 { task_id }
    loop poll until done
        W->>E: GET /status/{task_id}
        E-->>W: { status }
    end
    W->>E: GET /result/{task_id}
    E-->>W: GeoTIFF bytes
    W->>W: GeoTIFF → PNG
    W->>FS: write {hash}.png
    W->>API: UPDATE render row status=ready, bounds, asset_filename

    UI->>API: GET /rf-propagation/ (polling, 5s)
    API-->>UI: { status: ready, asset_url, bounds }
    UI->>FS: GET {asset_url} (public PNG)
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

### Cancelling / dismissing a render

There are two flavours of "stop" for non-`ready` rows, both scoped to a
single node and both requiring the same permission as `recompute`:

- **`POST .../rf-propagation/cancel/`** — audit-preserving. Flips any
  `pending`/`running` rows to `failed` with
  `error_message="Cancelled by user"` and stamps `completed_at`. The
  row stays in the database so operators can see _why_ a render was
  aborted. `failed` rows are untouched (nothing to cancel).
- **`POST .../rf-propagation/dismiss/`** — destructive. Deletes every
  non-`ready` row for the node (`pending`, `running`, **and**
  `failed`). Returns `{ "deleted": <count> }`. Use this from the UI
  when the operator clicks "Cancel" (while in flight) or "Dismiss"
  (on a failed row) — the end state is the same: the row is gone and
  the next recompute starts from a clean slate.

The worker is resilient to both: it performs three checks and treats
"row gone" (`DoesNotExist`) and "row in terminal state" the same way
— log and bail without writing:

1. On task pickup — skip if the row is already terminal (cancel) or
   missing (dismiss).
2. Just before the engine call — avoids the expensive roundtrip.
3. After the engine returns and the PNG is on disk — the worker
   refuses to revive a cancelled/dismissed row. The PNG stays on disk
   (it is content-addressed, so retention will reap it if nothing
   else references the hash).

There is no way to interrupt a running `/predict` call on the engine
side, so a cancel/dismiss during engine polling will still let the
current engine request finish; the worker just won't mark the row
`ready`.

Typical flows:

- Render is stuck in `pending` (e.g. worker was down, engine URL was
  misconfigured) → operator hits **dismiss** and then **recompute**.
- Engine returns a permanent `422` for an unfixable profile → row
  lands in `failed` → operator fixes the profile, clicks **dismiss**
  on the error card, then **recompute**.

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

## PNG overlay transparency

After GeoTIFF→PNG, pixels within **`RF_PROPAGATION_NODATA_TOLERANCE`**
of **`RF_PROPAGATION_NODATA_RGB`** (comma-separated `R,G,B`, default
`0,0,0`) are written with alpha 0 so the Leaflet basemap shows through
outside the tinted coverage.

## Environment variables

| Variable | Default | Where used | Notes |
| --- | --- | --- | --- |
| `RF_PROPAGATION_ENGINE_URL` | _(empty)_ | worker | Internal URL of the engine, e.g. `http://rf-propagation:8080`. Required for real renders. |
| `RF_PROPAGATION_ASSET_DIR` | `/var/meshflow/generated-assets/rf-propagation` | api + worker | Mounted from the `rf_assets` named volume; must be shared between `api` and `celery-rf-worker`. |
| `RF_PROPAGATION_IMAGE_TAG` | `latest-dev` | compose | Tag for the engine image. |
| `RF_PROPAGATION_RENDER_VERSION` | `2` | api + worker | Bump to invalidate all cached renders. |
| `RF_PROPAGATION_NODATA_RGB` | `0,0,0` | api + worker | RGB colour treated as transparent background in the PNG overlay. |
| `RF_PROPAGATION_NODATA_TOLERANCE` | `8` | api + worker | Per-channel distance from nodata RGB (0–255) to clear alpha. |
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
