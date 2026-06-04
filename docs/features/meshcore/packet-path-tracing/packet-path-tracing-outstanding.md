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

- [x] **[meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)** — HeardPathMap logical path per feeder ([ui#322](https://github.com/pskillen/meshflow-ui/pull/322)): dashed schematic hop chain, per-feeder paths in heard dialog.

## Geographic path on maps

- [x] **Geographic hop placement (message heard, partial)** — [ui#322](https://github.com/pskillen/meshflow-ui/pull/322): `HeardPathGeoMap` draws polylines when hop `position` values exist; partial segments when only some hops resolve. `path_known` still requires all hops resolved **with** positions (ADR).
- [x] **Wire message `heard[]` to segment resolution** — [api#395](https://github.com/pskillen/meshflow-api/pull/395): `bulk_format_path_hops` reads `MeshCorePathSegmentResolution` + guarded suffix auto-matcher; `path_hash_mode` / `path_hash_size` on `heard[]`.
- [ ] **M7 realtime/history maps** ([meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309)) — edge-based geographic and logical topology; depends on API M5/M6.
- [ ] **Sync [tier-2-heard-resolution.md](./tier-2-heard-resolution.md)** with shipped auto-matcher and `candidates[]` (doc still says “no heuristics in v1”).

Until all hops resolve with positions, operators should treat geo lines as **best-effort**; hash chains remain list-order evidence when resolution is incomplete.

---

## Carried from prior passive slice

- [ ] **Proven hash → `ObservedNode` matcher (M3 / rollups)** — spike still **unproven** for authoritative identity ([traceroute ADR-0001 §A](../../traceroute/adr/0001-mc-path-hash-resolution.md)). **Display-only** guarded suffix matcher for message `heard[]` shipped in [api#395](https://github.com/pskillen/meshflow-api/pull/395) (addendum in same ADR); ambiguity → `candidates[]`, no map placement for ambiguous hops.
- [ ] **`resolved_path` on `GET /api/meshcore/packets/`** — deferred from #360 (message API only). Optional; revisit alongside the edges API.
- [ ] **Upload `rx_log_data` PATH-only frames** — bot still skips non-ADVERT `rx_log_data` except TEXT_MSG/PATH typenames added for tier-1 twin; PATH-only relays without a correlatable text row may still be missing (M1 capture / bot follow-up of [#119](https://github.com/pskillen/meshflow-bot/issues/119)).

---

## Heard dialog UX (discovered 2026-06-04)

- [x] **Sender “unknown” vs channel list** — [ui#322](https://github.com/pskillen/meshflow-ui/pull/322): `resolveHeardPathSender` sets `identified` from a single `mc_sender_candidate` without requiring position; `HopPositionIcon` and geo map use position only.

---

## Capture gaps to confirm during M1/M2

- [x] `path_hash_size` / `path_hash_mode` persisted on `MeshCorePacketObservation` (M1 api + bot).
- [ ] `path_update` carries `public_key` only (no path hash in captures) — capture for possible future binding, not as a current resolver source.
- [ ] `trace_data` relationship to path hashes / active traces unconfirmed (M2 spike).

---

## Message path data chain (confirmed — pre-prod Jun 2026)

**Symptom (baseline):** Message “Heard” UI and `GET` message `heard[]` show observers but **no hop chain** for most MeshCore channel/contact text on pre-prod, even though M1 edge rollups exist.

**Update (post tier-1 [#390](https://github.com/pskillen/meshflow-api/pull/390)):** Some rows now have `path_hashes` on the text observation when a PATH/TEXT_MSG twin merged in-window (e.g. `☘️GI7ULG☘️: Test` — 3 segments). Overall rate remains low (~4% on 2026-06-03 sample); see [bug-no-path-info.md](./bug-no-path-info.md).

**Not the cause:** Single feeder (one observation per `packet_id` is expected). API heard assembly and UI behave correctly when `MeshCorePacketObservation.path_hashes` is set on the **same** packet as `TextMessage.original_mc_packet` (see `text_messages/tests/test_heard_api.py`).

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

- [x] **Tier 1 — server-led ingest** — [#385](https://github.com/pskillen/meshflow-api/issues/385) / [api#390](https://github.com/pskillen/meshflow-api/pull/390) merged: twin-merge, bot TEXT_MSG/PATH upload. Design: [tier-1-message-path-twin.md](./tier-1-message-path-twin.md).
- [x] **Tier 2 — heard resolution (display)** — [api#395](https://github.com/pskillen/meshflow-api/pull/395), [ui#322](https://github.com/pskillen/meshflow-ui/pull/322) open; design [tier-2-heard-resolution.md](./tier-2-heard-resolution.md).
- [ ] **Confirm with M2 spike** — whether `path_hash_mode` changes segment identity when we do get text paths (composite key already used in #395 for heard).
- [ ] **Re-run pre-prod metrics** after tier-1 on all feeders — `meshflow-api/Meshflow/ai-env` + Django shell or `MeshFlow/.cursor/skills/preprod-database/scripts/query-preprod.sh` (auto-detects api `ai-env`).

---

## Cross-links

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic and this file as milestones land.
- [ ] Keep [traceroute/meshcore-path-outstanding.md](../../traceroute/meshcore-path-outstanding.md) pointed here for the active-vs-passive split.
