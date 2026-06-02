# MeshCore passive packet path — outstanding

Items **skipped**, **incomplete**, or **discovered during planning** — not the milestone backlog (that lives in the plan and [#267](https://github.com/pskillen/meshflow-api/issues/267) sub-issues).

**Tracking:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267)

---

## Open decisions (gate later milestones)

- [ ] **Meaning of `path_hash_mode`** — does it change how a segment is derived/interpreted, and therefore whether `(hash_mode, hash_size, segment_hash)` is the correct identity key? Resolved by the M2 spike, informed by the M1 diagnostic UI (segment distribution by mode/size). See [ADR-0001 segment identity](adr/0001-meshcore-packet-path-tracing-subsystem.md).
- [ ] **Centrality compute location** — Postgres vs Neo4j for router/centrality metrics (M6). Resolved by/after M2 + M4.

**Note:** M1 now ships a read/annotate segments API and a diagnostic UI MVP specifically so these M2 decisions can be made from observed data rather than in the abstract.

---

## Message heard map (UI — logical layout, not M7)

- [ ] **[meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)** — HeardPathMap logical path per feeder: dashed schematic hop chain (one node per hash segment), **not** placed at map coordinates; keep sender/feeder at geo positions when known. Feeder list below graph shows **each observer’s distinct path** beside its row. Uses existing `heard[]` `path_hashes` / `resolved_path` from #360; no new API.

## Geographic path on maps (future milestone — plan explicitly)

The logical heard-map slice above is **not** a substitute for placing hops at real coordinates. A later plan/milestone must cover:

- [ ] **Geographic hop placement** — when M2/M3 (or manual segment annotation) yields `ObservedNode` positions for path segments, message heard map and/or M7 topology UI should render hops at **lat/lng** (and set `path_known` only when all hops are resolved per ADR).
- [ ] **Wire message `heard[]` to segment resolution** — optional read path from `MeshCorePathSegmentResolution` (or resolver output) so the heard dialog benefits from staff annotations / proven matcher without duplicating rollup tables in the client.
- [ ] **M7 realtime/history maps** ([meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309)) — edge-based geographic and logical topology; depends on API M5/M6.

Until then, operators should assume heard-map paths are **list-order hash evidence**, not RF geography.

---

## Carried from prior passive slice

- [ ] **Proven hash → `ObservedNode` matcher** — still unproven; no production matcher until [traceroute ADR-0001 §A](../../traceroute/adr/0001-mc-path-hash-resolution.md) documents a safe rule. Gates M3. Tests must reject suffix/prefix/recency heuristics.
- [ ] **`resolved_path` on `GET /api/meshcore/packets/`** — deferred from #360 (message API only). Optional; revisit alongside the edges API.
- [ ] **Upload `rx_log_data` PATH-only frames** — bot still skips non-ADVERT `rx_log_data`; needed for relays with `path_len > 0` and no business message (M1 capture / bot follow-up of [#119](https://github.com/pskillen/meshflow-bot/issues/119)).

---

## Capture gaps to confirm during M1/M2

- [x] `path_hash_size` / `path_hash_mode` persisted on `MeshCorePacketObservation` (M1 api + bot).
- [ ] `path_update` carries `public_key` only (no path hash in captures) — capture for possible future binding, not as a current resolver source.
- [ ] `trace_data` relationship to path hashes / active traces unconfirmed (M2 spike).

---

## Message path data chain (confirmed — pre-prod Jun 2026)

**Symptom:** Message “Heard” UI and `GET` message `heard[]` show observers but **no hop chain** for MeshCore channel/contact text on pre-prod, even though M1 edge rollups exist and the heard-map UI (#311) is wired to `path_hashes`.

**Not the cause:** Single feeder (one observation per `packet_id` is expected). API heard assembly and UI #311 behave correctly when `MeshCorePacketObservation.path_hashes` is set on the **same** packet as `TextMessage.original_mc_packet` (see `text_messages/tests/test_heard_api.py`).

### Pre-prod evidence (read-only DB, one feeder)

| Metric | Value |
| --- | --- |
| Observations with non-empty `path_hashes` | 754 |
| Event type for those rows | **100%** `rx_log_data` (stored as `advert` ingest) |
| `channel_text` observations with `path_hashes` | **0** (746 `channel_text` rows without path) |
| MeshCore `TextMessage` rows with path on linked packet observation | **0** |
| Packets with >1 observation | **0** (one feeder) |

M1 rollups on pre-prod are fed by **overheard ADVERT** frames (`rx_log_data` → `payload_typename == ADVERT`), not by channel-message ingest.

### End-to-end chain (logic confirmed)

```text
channel_message (bot) → channel_text (API) → TextMessage.original_mc_packet
  → heard[] reads obs.path_hashes on THAT packet  →  empty today

rx_log_data ADVERT only (bot) → advert (API) → observation.path_hashes populated
  → no TextMessage link  →  does not appear in message heard[]
```

1. **High-level decode (`channel_message`, `contact_message`)** — captures include `path_len` and often `path_hash_mode`, but **usually no `path` hex** (see meshflow-bot `docs/meshcore_packets/channel_messages/*.json`). Without `path`, ingest cannot populate `path_hashes` (bot today only forwards a pre-split list when `path` is present; API persists what the bot sends).

2. **Low-level decode (`rx_log_data`)** — ADVERT (and PATH) frames **do** include `path` + `path_hash_size` in captures (see `docs/meshcore_packets/rx_log_data/*ADVERT*.json`). Bot uploads **ADVERT `rx_log_data` only**; TEXT_MSG / PATH / etc. are skipped (`MeshCoreSkipUpload`) per [packet-ingestion/meshcore.md](../../packet-ingestion/meshcore.md).

3. **API** — no payload-type filter on `path_hashes`; M1 segment/edge tasks consume whatever observations exist.

### Design constraint: thin bot, fat server

Meshflow bots should stay **deploy-light**: forward captures with minimal transformation. **Maintainable path logic belongs on the API** (ingest normalization, dedup, rollups, heard assembly, resolution).

Implications for closing this gap (direction only — not scheduled here):

| Approach | Bot change | Server work |
| --- | --- | --- |
| **A. Ingest more `rx_log_data`** (TEXT_MSG / PATH with `path` on wire) | Thin: upload additional typename(s) as `raw` or mapped payload types; no hash splitting | Ingest serializer splits `path` → `path_hashes`; correlate to `TextMessage` via `pkt_hash` / time / dedup (needs design) |
| **B. Store decode metadata + raw** on observation | Thin: pass through `path_len`, `path_hash_mode`, optional `raw_hex` from envelope | Server decodes or joins to PATH/`rx_log_data` rows if/when ingested |
| **C. Wait for meshcore lib** to add `path` on `channel_message` | None if library starts emitting `path` | Existing ingest path may “just work” once `path` arrives in JSON |

**Avoid** adding bot-side `_path_hashes()`-style rules, new upload filters, or message↔packet correlation — that duplicates server responsibility and is painful to roll out per feeder.

### Sample references

| Source | `path` present? |
| --- | --- |
| `channel_message` dump `20260507_094941_052599.json` | No (`path_len`, `path_hash_mode` only) |
| `rx_log_data` ADVERT `20260506_211819_583174.json` | Yes |
| `rx_log_data` PATH `20260506_211515_351329.json` | Yes (not uploaded today) |

### Follow-up (tracking)

- [ ] **Tier 1 — server-led ingest (ship)** — [#385](https://github.com/pskillen/meshflow-api/issues/385): `path_hashes` on observation tied to `original_mc_packet` for channel `TextMessage` traffic; thin bot upload of TEXT_MSG/PATH `rx_log_data`; API twin-merge. Design: [tier-1-message-path-twin.md](./tier-1-message-path-twin.md).
- [ ] **Confirm with M2 spike** — whether `path_hash_mode` changes segment identity when we do get text paths.
- [ ] **Optional:** re-run pre-prod queries after deploy (`Meshflow/ai-env` + Django shell; local skill `MeshFlow/.cursor/skills/preprod-database/`) — breakdown by `payload_type` + `event_type`.

---

## Cross-links

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic and this file as milestones land.
- [ ] Keep [traceroute/meshcore-path-outstanding.md](../../traceroute/meshcore-path-outstanding.md) pointed here for the active-vs-passive split.
