# Tier 1 — message path via rx_log decoded twin

**Tracking:** [meshflow-api#385](https://github.com/pskillen/meshflow-api/issues/385)

## Problem

Decoded `channel_message` ingest (`channel_text`) usually has `path_hash_mode` / `path_hash_size` but **no `path` hex**. Companion `rx_log_data` **TEXT_MSG** / **PATH** frames carry `pkt_hash` and often `path`. Heard reads `path_hashes` on observations for `TextMessage.original_mc_packet` only.

## Approach (MVP)

**Thin bot:** upload TEXT_MSG and PATH `rx_log_data` as `payload_type: raw` (forward envelope + `path_hashes` when present).

**Fat API:** after ingest, **bidirectional twin merge** within `MESHCORE_DECODED_TWIN_WINDOW_SECONDS` (default 30s, see `meshcore_packets.services.dedup.decoded_twin_window`):

| Order | Action |
| --- | --- |
| `channel_text` then `raw` TEXT_MSG/PATH | On `raw` ingest, copy path fields onto the matching `MeshCoreTextPacket` observation (same feeder) |
| `raw` then `channel_text` | On `channel_text` ingest, copy path from recent matching `raw` observation |

Matching rules (MVP):

- Same `observer` (feeder `ManagedNode`).
- `rx_time` within decoded-twin window.
- Target packet: `CHANNEL_TEXT` only (not DMs).
- If multiple candidates: narrow by `channel_idx` in `raw_json` vs text packet / observation `channel` when available; if still ambiguous, skip merge (debug log).

Raw rows are still stored (M1 rollups / debugging). Heard uses the **text** packet observation after merge.

## Failure modes

- No twin in window → `path_hashes` stay empty on text observation; heard schematic empty.
- `channel_message` without companion `rx_log_data` on that feeder → no path (ops / library gap).
- Full `raw_packet_fk` linkage → deferred to [ADR-0004](../../packet-ingestion/adr/0004-mc-dedup-key.md) / [#276](https://github.com/pskillen/meshflow-api/issues/276).

## Implementation

- `meshcore_packets.services.path_hashes` — server-side `path` hex split when bot omits `path_hashes`.
- `meshcore_packets.services.path_twin` — `sync_path_to_channel_text_twin`, `sync_path_from_rx_log_twin`.
- Wired from `MeshCorePacketIngestSerializer.create` after `_ensure_observation`.

## Verification

See [#385](https://github.com/pskillen/meshflow-api/issues/385) acceptance criteria and [phase-3-outstanding.md](../phase-3-outstanding.md).
