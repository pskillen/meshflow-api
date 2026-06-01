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

## Cross-links

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic and this file as milestones land.
- [ ] Keep [traceroute/meshcore-path-outstanding.md](../../traceroute/meshcore-path-outstanding.md) pointed here for the active-vs-passive split.
