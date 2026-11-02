# Nearby infrastructure

A public, read-only endpoint that answers "which Meshtastic routers and
repeaters are near this point?".

## Purpose

Third-party map clients can show infrastructure nodes without a Meshflow login.
The first consumer is Codeplug Studio's Nearby repeaters tool
([pskillen/codeplug-studio#1518](https://github.com/pskillen/codeplug-studio/issues/1518)).
Tracked by [#432](https://github.com/pskillen/meshflow-api/issues/432).

## Endpoint and parameters

`GET /api/nodes/observed-nodes/infrastructure/nearby/`

| Param | Required | Default | Notes |
| --- | --- | --- | --- |
| `lat` | yes | | Degrees, -90 to 90. 400 when missing, not a number or out of range. |
| `lon` | yes | | Degrees, -180 to 180. Same errors as `lat`. |
| `radius_km` | no | 25 | Clamped to 1-100. |
| `last_heard_within_days` | no | 30 | Integer, clamped to 1-365. Nodes never heard are excluded. |
| `include_client_base` | no | false | `true` also includes `CLIENT_BASE` nodes, as on `/infrastructure/`. Anything else is false. |

Errors are `400 {"error": "<message>"}`.

## Response

```json
{
  "results": [
    {
      "internal_id": "3f2b6c1e-8a4d-4c55-9a53-0d7a1e2b9c10",
      "node_id_str": "!0000a001",
      "long_name": "Example Router",
      "short_name": "EXR",
      "meshtastic_role": 2,
      "meshtastic_role_label": "ROUTER",
      "meshtastic_hw_model": "RAK4631",
      "last_heard": "2026-11-02T11:03:17Z",
      "latitude": 55.79,
      "longitude": -4.22,
      "altitude": 190.0,
      "distance_km": 3.4
    }
  ],
  "meta": { "lat": 55.8, "lon": -4.2, "radius_km": 25.0, "last_heard_within_days": 30, "count": 1, "truncated": false }
}
```

- Unpaginated, nearest first (ties broken by `node_id_str`), capped at 500.
- `lat` and `lon` are rounded to 3 decimal places (about 110 m) and `radius_km`
  to 1 after clamping. `meta` echoes the values actually used.
- `distance_km` is rounded to 2 decimal places. `altitude` is returned as stored,
  so a float (`190.0`) or `null`; clients must accept both `190` and `190.0`.
- `count` is the number of results returned (at most 500). `truncated` is true
  when more nodes matched than were returned.

## Privacy

Only Meshtastic nodes with an infrastructure role (ROUTER, ROUTER_CLIENT,
REPEATER, ROUTER_LATE), plus CLIENT_BASE on request, are returned. Client
nodes are never included. These nodes broadcast their position publicly on the
mesh. Nodes with no position (or a 0,0 placeholder) are excluded. The
serializer exposes only the fields above: no owner, claim, metrics, MAC or
public key. Guest redaction on the other endpoints is unchanged; see
[permissions](../../permissions/README.md).

## CORS and auth

- No authentication. Any `Authorization` header (valid or not) is ignored.
- GET only; other methods return 405.
- Guest-throttled like the other guest reads: `guest_burst` per client IP
  (`THROTTLE_GUEST_BURST`, default 120/min; see
  [permissions](../../permissions/README.md)). Over the limit returns 429 with
  `Retry-After`.
- Every response (200, 400, 405 and 429) carries `Access-Control-Allow-Origin: *`.
  When the request `Origin` is in `CORS_ALLOWED_ORIGINS` (the Meshflow SPA),
  django-cors-headers replaces it with the echoed origin and adds
  `Access-Control-Allow-Credentials: true`; browsers accept either.
- Send a simple GET with no custom headers (no `Authorization`, no
  `Content-Type`). Browsers then skip the preflight. A preflight `OPTIONS` from a
  foreign origin is answered by the CORS middleware without
  `Access-Control-Allow-Origin` and will fail.

## Caching

Responses are cached in the Django cache (Redis DB 2) under
`nodes:infra_nearby:v1:{lat}:{lon}:{radius}:{days}:{cb}`, built from the rounded
and clamped parameters. TTL is `NEARBY_INFRASTRUCTURE_CACHE_SECONDS` (default 60;
`0` disables caching entirely). A cache failure is logged and the endpoint falls
back to the database. 200 responses carry `Cache-Control: public, max-age=<ttl>`.
See [REDIS.md](../../REDIS.md) and [ENV_VARS.md](../../ENV_VARS.md).

## Implementation

- Service: `Meshflow/nodes/services/nearby_infrastructure.py` (parameter parsing,
  query, cache wrapper).
- View: `ObservedNodeViewSet.infrastructure_nearby` in `Meshflow/nodes/views.py`
  (`authentication_classes=[]`; `get_permissions` has an explicit `AllowAny` branch).
- Serializer: `NearbyInfrastructureNodeSerializer` in `Meshflow/nodes/serializers.py`.
- Query: a SQL bounding box on `NodeLatestStatus` latitude/longitude, then
  haversine in Python for the exact radius and distance. The box handles the
  antimeridian (longitude wrap) and skips the longitude filter near the poles.
- Tests: `Meshflow/nodes/tests/test_nearby_infrastructure.py`.

## Out of scope / future

- MeshCore repeaters (possibly via a `protocol` param).
- The `http://` pagination `next` link behind the proxy (this endpoint is unpaginated).
