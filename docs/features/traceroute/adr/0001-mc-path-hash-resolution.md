# ADR-0001 — MeshCore path hash resolution

**Status:** Accepted (v1 display-only)  
**Date:** 2026-05-27  
**Tracking:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267), [#360](https://github.com/pskillen/meshflow-api/issues/360)

## Context

MeshCore forwarded packets may include a repeater **path** as concatenated hex bytes split by `path_hash_size` (see [MESHCORE_PACKET_FIELDS.md](../../packet-ingestion/MESHCORE_PACKET_FIELDS.md)). Feeders upload these as `path_hashes[]` on ingest. Multi-feeder dedup stores one `MeshCoreRawPacket` per on-air transmission but one `MeshCorePacketObservation` per feeder, each with its own path ([#369](https://github.com/pskillen/meshflow-api/issues/369)).

Meshtastic traceroute enrichment maps numeric `node_id` values in `route` JSON to `ObservedNode` rows. MeshCore path segments are **short opaque hashes** (often 1–3 bytes per hop), not full pubkeys.

[ADR-0001 (node identity)](../../packet-ingestion/adr/0001-mc-node-identity.md) defines `mc_pubkey` (64 hex) and `mc_pubkey_prefix` (12 hex) for node identity. Nothing in that ADR or in capture docs proves that an arbitrary path segment equals a suffix or prefix of those fields.

## Section A — Spike (hash derivation)

**Reviewed sources:**

| Source | Finding |
| --- | --- |
| Capture JSON (`docs/packets/meshcore/`) | `path`, `path_len`, `path_hash_size` on `rx_log_data` and decoded messages; segments are hex substrings of `path`. |
| `meshflow-bot` `MeshCorePacketSerializer._path_hashes()` | Splits `path` by `path_hash_size`; no semantic mapping to pubkeys. |
| `meshcore_py` / firmware | No stable, documented mapping from 1–3 byte path hash → 32-byte Ed25519 pubkey in Meshflow docs at spike time. |

**Conclusion (spike outcome): unproven**

We can reliably **parse and display** path segments per feeder observation. We **cannot** safely map segments to `ObservedNode` rows using `mc_pubkey__iendswith`, prefix match, or `last_heard` tie-breaks without a spec-backed algorithm. False positives would mislead map and traceroute-style UI.

**Follow-up:** Revisit when upstream (MeshCore / `meshcore_py`) documents hash derivation, or when we ingest `path_update` / other events that carry explicit hash→pubkey bindings.

## Section B — v1 API behaviour (shipped in #267 passive path)

1. **`path_hashes`** on `MeshCorePacketObservation` only (not on deduped raw packet row).
2. **`resolved_path`** on message `heard[]` — display hops, not Meshtastic `route_nodes`:

```json
{
  "hash": "f3bcf1",
  "status": "unknown",
  "node_id_str": null,
  "internal_id": null,
  "long_name": null,
  "ambiguous": false
}
```

3. **`path_known`:** `false` in v1 (UI draws dashed sender→feeder lines; hash tooltips at segment midpoints when applicable).
4. **No DB lookup** for hop→node in v1. `status=resolved` and non-null `internal_id` are reserved for a future proven matcher.

## Consequences

- Message heard map shows sender, feeder position(s), and **dashed** paths; hop labels show raw hash hex.
- UI must not link unknown hops to node detail pages.
- When a proven matcher lands, add tests that fail if heuristic matching is reintroduced without ADR update.

## Addendum (2026-06) — message heard auto-matcher

`bulk_format_path_hops` still prefers **`MeshCorePathSegmentResolution`** rows keyed by `(hash_mode, hash_size, segment_hash)`.

When no staff row applies, a **guarded suffix matcher** runs:

- Segment hex must match the **suffix** of `mc_pubkey_prefix` or `mc_pubkey` on `ObservedNode` (case-insensitive).
- **One** match → `status=resolved` with node fields and position when available.
- **Multiple** matches → `status=ambiguous` with `candidates[]` (same shape as `McSenderCandidate`); UI must not place ambiguous hops on the map.

This is display-only for message `heard[]`; it does not prove on-air identity. Tests in `meshcore_packets/tests/test_path_resolution.py` lock ambiguity behaviour.
