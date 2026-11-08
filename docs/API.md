# Meshflow API Documentation

**Authorization and endpoint access levels:** see **[permissions/README.md](permissions/README.md)** (canonical).

**OpenAPI contract:** [`openapi.yaml`](../openapi.yaml) at the repository root.

## Authentication endpoints

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/token/` | POST | Obtain JWT pair |
| `/api/token/refresh/` | POST | Refresh JWT |
| `/api/token/verify/` | POST | Verify JWT |

## Other areas

| Area | Base path |
|------|-----------|
| Nodes | `/api/nodes/` |
| Constellations | `/api/constellations/` |
| Messages | `/api/messages/` |
| Stats | `/api/stats/` |
| Traceroutes | `/api/traceroutes/` |
| Packet ingest (legacy, node number in path) | `/api/packets/`, `/api/v3/packets/` |
| Feeder API v4 (key-scoped) | `/api/v4/feeder/` |
| MeshCore | `/api/meshcore/` |

See OpenAPI for request/response schemas.

## Feeder API v4

Feeder bots authenticate with a Node API key (`X-API-KEY`). On the v4 URLs the key alone identifies
the feeder, so it must be linked to **exactly one** active feeder: **one API key per feeder**. There is
no node number in the path, so a Meshtastic 2.8 feeder whose node number changes keeps working.

| Method + path | Protocol | Same body and response as |
|---------------|----------|---------------------------|
| `GET /api/v4/feeder/identity/` | any | (new) which feeder this key identifies; the bot's v4 probe |
| `PUT\|POST\|PATCH /api/v4/feeder/bot-version/` | any | `/api/v3/packets/{node_id}/bot-version/` |
| `POST /api/v4/feeder/meshtastic/ingest/` | Meshtastic | `/api/v3/packets/{node_id}/ingest/` |
| `POST /api/v4/feeder/meshtastic/nodes/` | Meshtastic | `/api/v3/packets/{node_id}/nodes/` (strict `meshtastic_*` wire) |

Errors are 403 with `{"detail": "<text>", "code": "<code>"}`:

| `code` | Meaning |
|--------|---------|
| `feeder_not_linked` | The key has no active feeder |
| `shared_api_key` | The key is linked to more than one active feeder. Mint one key per feeder on the API keys page; the legacy URLs still accept shared keys |
| `feeder_protocol_mismatch` | A MeshCore feeder called a `meshtastic/` path |

A bad or missing key is a 401, as on the legacy URLs. A reported node number
(`X-Meshtastic-Feeder-Node-Num`) that differs from the stored one is **never** an error: it is recorded on
the ManagedNode and shown as `identity_mismatch` on `identity/`. The WebSocket takes
`ws/nodes/?api_key=<key>&feeder_scoped=1` for the same single-feeder rule.

The legacy URLs (`/api/packets/{node_id}/…`, `/api/v3/packets/{node_id}/…`, `/api/meshcore/feeders/{prefix}/…`)
are unchanged, shared keys included. Their use is tracked for retirement: Prometheus
`meshflow_feeder_api_requests_total{api,protocol,endpoint,status_class}` and
`meshflow_feeder_auth_rejections_total{api,code}`, plus per-feeder `feeder_api_generation` and
`legacy_api_last_used_at` on ManagedNode (admin filter "On legacy URLs (last 7 days)"). MeshCore v4 URLs
are not built yet. Design: [ADR-0005](features/packet-ingestion/adr/0005-feeder-scoped-auth.md).
