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
| Packet ingest | `/api/packets/` |
| MeshCore | `/api/meshcore/` |

See OpenAPI for request/response schemas.
