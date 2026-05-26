# Meshflow

Meshflow is a platform for monitoring and administering a country-wide
[Meshtastic](https://meshtastic.org/) network. It collects raw mesh packets from
a fleet of geographically distributed monitoring nodes ("feeders"), normalises
them into a shared business model, and exposes the result through a REST and
WebSocket API plus a React SPA.

This README is a high-level summary of what Meshflow does. The deep dives for
each feature live in `[docs/features/](/)`, and other cross-cutting
concerns (auth, packet ingestion, deduplication, recency, Redis layout, etc.)
live in their own files in `[docs/](../)`.

## System Shape

```text
Meshtastic radios
       │  (RF mesh)
       ▼
Managed feeder nodes  ─── meshtastic-bot (Python) ──► Meshflow API
                                                      │
                                                      ├─ Postgres (relational data)
                                                      ├─ Neo4j   (mesh topology / traceroutes)
                                                      ├─ Redis   (Channels, Celery, cache, RF)
                                                      └─ Celery workers (ingestion, monitoring,
                                                                        traceroutes, RF render,
                                                                        notifications)
                                                      │
                                                      ▼
                                              meshtastic-bot-ui (React SPA)
```

Components:

- **meshtastic-bot** — Python bot running next to each managed Meshtastic
radio. Captures raw packets and uploads them to the API; receives commands
(e.g. traceroute requests) over WebSocket.
- **meshflow-api** — Django REST Framework API, Channels for WebSockets, and
Celery workers for asynchronous processing.
- **meshflow-rf-propagation** — thin Docker wrapper around
[meshtastic-site-planner](https://github.com/meshtastic/meshtastic-site-planner)
used by the API for predicted RF coverage rendering.
- **meshtastic-bot-ui** — React SPA, the user-facing front end.

## Core Domain Model


| Model                                                                                                                                                           | Purpose                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ObservedNode`                                                                                                                                                  | A Meshtastic node heard on the mesh, either inferred from packet observations or from a `NodeInfo` broadcast. Has `last_heard`, position, device metrics, environment metrics.                                  |
| `ManagedNode`                                                                                                                                                   | A feeder node owned and operated by a volunteer. 1:1 with an `ObservedNode`; ingests packets through a `meshtastic-bot` instance authenticated via `NodeAPIKey`.                                                |
| `NodeOwnerClaim`                                                                                                                                                | Claim record proving end-user ownership of an `ObservedNode`. The user is given a 3-word secret token and must DM it via the mesh; receipt by any feeder confirms physical possession.                          |
| `Constellation`                                                                                                                                                 | Logical, geographical grouping of nodes (e.g. *Central Belt Scotland*, *Northern Ireland*). Used for regional separation, message channels, and coverage views. Currently primarily attached to `ManagedNode`s. |
| `MtRawPacket` and friends (`TextMessagePacket`, `TraceroutePacket`, `PositionPacket`, `NodeInfoPacket`, `TelemetryPacket`, `RoutingAppPacket`, `EncryptedPacket`) | The captured wire-level packet data. See [packet-ingestion/](packet-ingestion/) and [packet-ingestion/PACKET_FIELDS.md](packet-ingestion/PACKET_FIELDS.md).                                                     |
| `TextMessage`, `Position`, `NodeInfo`, `DeviceMetrics`, `EnvironmentMetrics`                                                                                    | Normalised business-level views derived from raw packets.                                                                                                                                                       |
| `AutoTraceRoute`                                                                                                                                                | Persisted traceroute request (manual, scheduled, monitoring, external, DX, or new-node baseline) with its result.                                                                                               |


Lifecycle: nodes are discovered via packet ingestion, optionally claimed by a
user via the 3-word DM token, and optionally promoted to a managed feeder. See
[features/node-lifecycle/](node-lifecycle/) for the full lifecycle and
removal flows.

## Features

### Packet ingestion & normalisation

The original purpose of the platform: distributed feeders capture the raw mesh
traffic — including both sides of conversations that any single listener would
miss — and the API normalises them into the domain models above. Ingestion is
deduplicated across feeders so packets observed by multiple monitors do not
double-count.

Reference: [packet-ingestion/](packet-ingestion/) (overview, dedup, packet
field reference); raw sample payloads in [`docs/packets/`](../packets/);
[`RECENCY.md`](../RECENCY.md) for `last_heard` semantics.

### Node map

Most Meshtastic nodes broadcast GPS positions. Meshflow plots the latest known
position of every observed node on a Leaflet map, with filters by constellation,
role, and recency window (2h / 24h / 7d / 30d / all).

### Text messages

Per-constellation view of public-channel (`LongFast`) text messages observed on
the mesh. Because feeders are geographically distributed, Meshflow can show
both sides of conversations even when no single radio could hear them all.
Realtime updates are pushed over WebSocket.

### Mesh infrastructure monitoring

A dedicated page surfacing the health of every node with an infrastructure
role (`ROUTER`, `REPEATER`, etc.) — battery, voltage, channel utilisation,
last heard. Used by operators to spot failing infra at a glance. Alert badges
in the UI sidebar surface active mesh-monitoring alerts on infra nodes.

### Traceroutes

Managed nodes can be instructed to run Meshtastic `traceroute` commands. The
scheduler picks random `(source, target)` pairs every 5–15 minutes to build a
picture of the mesh; users with the right permissions can trigger manual
traceroutes; mesh monitoring and DX monitoring use traceroutes for verification
and exploration; first-time observed nodes get a one-shot baseline traceroute.

Persisted results feed Neo4j, which powers:

- **History** — per-traceroute detail and filtering.
- **Geographic heatmap** — link quality (SNR) overlaid on the map.
- **Topology** — logical mesh graph (heat / SNR variants).
- **Per-feeder coverage** — which targets a single feeder can reach, with
reliability colouring.
- **Constellation coverage** — server-side H3-binned reach for an entire
constellation, optionally rendered as concave-hull polygons.

Trigger taxonomy and analytics ownership are documented in
[features/traceroute/](traceroute/).

### Mesh monitoring (NodeWatch)

Authenticated users can **watch** an observed node (their own claimed nodes,
or any infrastructure-role node). When a watched node is silent for longer
than its configured threshold, the system runs a verification round of
monitoring traceroutes from up to three nearby feeders. If the node still
cannot be reached before the deadline, it is treated as offline and watchers
are notified. Recovery (any fresh packet) clears the offline state.

Optional **low-battery alerts** fire when consecutive `DeviceMetrics` reports
fall below a configurable threshold.

Notifications are delivered via verified Discord DMs (see below).

Reference: [features/mesh-monitoring/](mesh-monitoring/).

### DX monitoring

Detects unusual long-distance mesh visibility events — a brand-new node
appearing well outside the local cluster, a previously-DX node returning after
a quiet period, or known distant nodes suddenly directly reachable. Suspected
causes include tropospheric ducting, airborne nodes, or temporary high-altitude
deployments.

Detection groups related observations into deduplicated `DxEvent` windows with
attached packet and (later) traceroute evidence. Delivered in phases — see
[features/dx-monitoring/](dx-monitoring/) for scope, current MVP, and
future detection ideas. The UI surface is currently staff-only.

### Weather

Some nodes broadcast environment metrics (temperature, humidity, pressure,
air quality, …). Meshflow plots these on a map with optional filtering to
exclude suspected indoor nodes, since outdoor weather data is the only useful
signal.

### RF propagation

Owners of observed nodes can request a predicted RF coverage map for their
hardware. The API stores radio profile inputs (`NodeRfProfile`), hashes them
into a cache key, queues a render through Celery, calls the
`meshflow-rf-propagation` Site Planner image, converts the returned GeoTIFF
into a PNG with bounds, and the SPA overlays it on the node map.

Reference: [features/rf_propagation/](rf_propagation/),
`[ENV_VARS.md](../ENV_VARS.md)` §10.

### Discord integration

Users can verify and link a Discord account to receive DMs from Meshflow —
mesh-monitoring offline alerts, low-battery alerts, and (future) DX
notifications. Verification, audit, and DM delivery live in the
`push_notifications` app. See [features/discord/](discord/).

### Stats & dashboard

The dashboard surfaces recent node counts across rolling windows, constellation
maps, and packet/throughput stats. The `stats` app produces the aggregated
counters; the SPA's `Dashboard` page is the primary consumer.

Reference: [packet-stats/](packet-stats/) — hourly `StatsSnapshot` collection,
live Meshtastic stats API, and MeshCore snapshot parity ([#329](https://github.com/pskillen/meshflow-api/issues/329)).

### Realtime (WebSocket)

The `ws` app exposes Channels consumers used for two distinct things:

- **Bot command channel** — `NodeConsumer` delivers traceroute and other
commands from the API to connected `meshtastic-bot` feeders.
- **UI live updates** — the SPA subscribes to message and node-event streams
for live dashboard / message-page updates.

## Cross-Cutting Reference

- `[permissions/README.md](../permissions/README.md)` (canonical access levels),
  `[AUTH.md](../AUTH.md)`, `[API_KEYS.md](../API_KEYS.md)`,
`[USER_ONBOARDING.md](../USER_ONBOARDING.md)` — authentication, JWT, social
auth, node API keys, user onboarding.
- `[API.md](../API.md)` — REST API conventions; `openapi.yaml` is the
canonical contract.
- [packet-ingestion/PACKET_FIELDS.md](packet-ingestion/PACKET_FIELDS.md),
  [`packets/`](../packets/) — wire-level packet shapes and field references.
- [packet-ingestion/DEDUPLICATION.md](packet-ingestion/DEDUPLICATION.md),
  [`RECENCY.md`](../RECENCY.md) — ingestion deduplication and recency /
  `last_heard` semantics.
- `[REDIS.md](../REDIS.md)` — Redis logical database layout (Channels, Celery
broker, cache, RF engine).
- `[ENV_VARS.md](../ENV_VARS.md)` — environment configuration.
- `[RELEASE.md](../RELEASE.md)` — release process.

## Django App Map


| App                    | Responsibility                                                                                       |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| `nodes`                | `ObservedNode`, `ManagedNode`, `NodeOwnerClaim`, `NodeLatestStatus`, `NodeAPIKey`, liveness helpers. |
| `constellations`       | Constellations, memberships, message channels.                                                       |
| `packets`              | Raw packet ingestion, normalisation, deduplication, signals.                                         |
| `text_messages`        | Normalised text messages and views.                                                                  |
| `traceroute`           | `AutoTraceRoute` lifecycle, scheduling, dispatch, packet completion.                                 |
| `traceroute_analytics` | Neo4j export, heatmap / coverage / reach pivots, stats endpoints.                                    |
| `mesh_monitoring`      | `NodeWatch`, `NodePresence`, `NodeMonitoringConfig`, verification Celery, alert summaries.           |
| `dx_monitoring`        | DX event detection, exploration, notification scaffolding.                                           |
| `rf_propagation`       | RF profile, render queue, Site Planner client, image pipeline.                                       |
| `push_notifications`   | Discord linking, audit, DM delivery.                                                                 |
| `stats`                | Aggregated packet / node statistics.                                                                 |
| `users`                | Auth, JWT, social auth, user preferences.                                                            |
| `common`               | Shared helpers (geo, mesh node ID conversion, etc.).                                                 |
| `ws`                   | Channels consumers — bot command channel and UI live updates.                                        |


## SPA Surface (meshtastic-bot-ui)

For reference, the navigable surface in the React SPA today:

- **Dashboard** — recent node counts, constellation map, packet stats.
- **Messages** — per-constellation `LongFast` history with live updates.
- **Nodes** — list + detail; sub-pages for *My nodes*, *Managed nodes*,
*Watches*, *DX monitoring* (staff), *Mesh infra*.
- **Weather** — environmental metrics map.
- **Traceroutes** — *History*, *Geographic*, *Topology*, *Coverage by node*,
*Constellation coverage*.
- **User** — profile, Discord linking, node settings, claim flow.

This list is the practical baseline for the meshcore adoption work — anything
new should plug in alongside these features and respect the existing model and
permission boundaries above.