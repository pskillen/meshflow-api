# Meshflow permissions (canonical)

**Status:** implemented (issue [#346](https://github.com/pskillen/meshflow-api/issues/346))

Meshflow is a **public mesh observatory** with a small set of global access levels. Constellation membership roles (`admin` / `editor` / `viewer`) are **removed**; `Constellation` remains organizational grouping only.

## Access levels

| Level | Identity | Read (summary) | Write (summary) |
|-------|----------|----------------|-----------------|
| **guest** | No JWT | Constellations, channels, messages, observed nodes (redacted), public stats/traceroute reads | Auth endpoints only |
| **user** | JWT | Guest + positions, ownership, personal resources | Claim own nodes; own settings |
| **feeder** | JWT + `feeder` group | User reads + operator tooling | API keys (any constellation); bot ingest via `NodeAPIKey`; **trigger traceroutes** |
| **admin** | `is_staff` | All surfaces including DX | Constellation CRUD; system admin; trigger traceroutes |

Feeder is granted via Django group `feeder` (migration: managed-node owners and former constellation editors/admins).

## Guest field redaction (observed nodes)

Stripped for guests: `latest_position`, `owner`, `claim`, `environment_settings_editable`, `rf_profile_editable`, `has_rf_profile`, `has_ready_rf_render`.

See [RF privacy](../features/rf_propagation/privacy.md) for propagation side channels.

## Access matrix (representative)

| Bundle | Endpoints | guest | user | feeder | admin |
|--------|-----------|-------|------|--------|-------|
| Auth | `/api/token/`, `/api/auth/*` | login only | yes | yes | yes |
| Constellations | `GET /api/constellations/` | yes | yes | yes | yes |
| Constellations write | `POST/PATCH/DELETE` | no | no | no | yes |
| Channels | `GET …/channels/` | yes | yes | yes | yes |
| Messages | `GET /api/messages/` | yes | yes | yes | yes |
| Observed nodes | `GET /api/nodes/observed-nodes/` | redacted | full | full | full |
| Recent counts | `GET …/recent_counts/` | yes | yes | yes | yes |
| Stats global | `GET /api/stats/global/` | yes | yes | yes | yes |
| Traceroutes read | `GET /api/traceroutes/` | yes | yes | yes | yes |
| Traceroute trigger | `POST …/trigger/` | no | no | yes | yes |
| API keys | `/api/nodes/api-keys/` | no | no | yes | yes |
| Ingest | `/api/packets/…`, `/api/meshcore/…` | no | no | key | key |
| Monitoring | `/api/monitoring/…` | no | yes | yes | yes |
| DX | `/api/dx/…` | no | no | no | yes |

Full inventory: see `implementation-status.md`.

## WebSocket

| Path | Auth | Level |
|------|------|-------|
| `ws/nodes/?api_key=` | Node API key | feeder (bot) |
| `ws/traceroutes/?token=` | JWT | user+ |

## UI

[meshflow-ui #298](https://github.com/pskillen/meshflow-ui/issues/298) — anonymous browsing. Route matrix: `meshflow-ui/docs/PERMISSIONS.md`.

## OpenAPI

Guest-readable `GET` operations use `security: []` where updated. Authenticated operations use `BearerAuth`. Ingest uses `NodeApiKeyAuth`.

## Related docs

- [API keys](../API_KEYS.md)
- [AUTH.md](../AUTH.md) (OAuth login flow)
- [Traceroute permissions (delta)](../features/traceroute/permissions.md)
- [Mesh monitoring permissions (delta)](../features/mesh-monitoring/permissions.md)

## Changelog

- **2026-05-25:** Guest read; remove `ConstellationUserMembership`; feeder group; traceroute trigger feeder/admin only.
