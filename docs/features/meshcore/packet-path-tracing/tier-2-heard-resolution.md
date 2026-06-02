# Tier 2 — Heard map resolution

**Tracking:** [#373](https://github.com/pskillen/meshflow-api/issues/373), [#374](https://github.com/pskillen/meshflow-api/issues/374)

## Behaviour

`GET /api/messages/text/` `heard[].resolved_path` is built from:

1. **`MeshCorePathSegmentResolution`** (M1) — staff `PATCH /api/meshcore/path-tracing/segments/` or rollup from passive traffic.
2. **No automatic suffix/recency heuristics** in v1 (await ADR #373 for proven matcher).

When a segment row is `status=resolved` with `observed_node` set, each hop includes `node_id_str`, `long_name`, and `position` (from `NodeLatestStatus`). `path_known` is true only when **every** hop is resolved **and** has a position.

## UI

[meshflow-ui](https://github.com/pskillen/meshflow-ui) `HeardPathGeoMap` draws polylines when `path_known` and hop `position` values are present (same pattern as Meshtastic heard paths).

## Code

- `meshcore_packets.services.path_resolution.bulk_format_path_hops` — segment table lookup.
- `text_messages` list view — bulk cache per page of messages.
