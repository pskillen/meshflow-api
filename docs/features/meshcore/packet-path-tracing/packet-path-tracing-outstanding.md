# MeshCore passive packet path — outstanding

Items **skipped**, **incomplete**, or **discovered during planning** — not the milestone backlog (that lives in the plan and [#267](https://github.com/pskillen/meshflow-api/issues/267) sub-issues).

**Tracking:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267)

---

## Open decisions (gate later milestones)

- [ ] **Meaning of `path_hash_mode`** — does it change how a segment is derived/interpreted, and therefore whether `(hash_mode, hash_size, segment_hash)` is the correct identity key? Resolved by the M2 spike, informed by the M1 diagnostic UI (segment distribution by mode/size). See [ADR-0001 segment identity](adr/0001-meshcore-packet-path-tracing-subsystem.md).
- [ ] **Centrality compute location** — Postgres vs Neo4j for router/centrality metrics (M6). Resolved by/after M2 + M4.

**Note:** M1 now ships a read/annotate segments API and a diagnostic UI MVP specifically so these M2 decisions can be made from observed data rather than in the abstract.

---

## Carried from prior passive slice

- [ ] **Proven hash → `ObservedNode` matcher** — still unproven; no production matcher until [traceroute ADR-0001 §A](../../traceroute/adr/0001-mc-path-hash-resolution.md) documents a safe rule. Gates M3. Tests must reject suffix/prefix/recency heuristics.
- [ ] **`resolved_path` on `GET /api/meshcore/packets/`** — deferred from #360 (message API only). Optional; revisit alongside the edges API.
- [ ] **Upload `rx_log_data` PATH-only frames** — bot still skips non-ADVERT `rx_log_data`; needed for relays with `path_len > 0` and no business message (M1 capture / bot follow-up of [#119](https://github.com/pskillen/meshflow-bot/issues/119)).

---

## Capture gaps to confirm during M1/M2

- [ ] `path_hash_size` / `path_hash_mode` not yet persisted on `MeshCorePacketObservation` (being addressed in M1 capture, api + bot).
- [ ] `path_update` carries `public_key` only (no path hash in captures) — capture for possible future binding, not as a current resolver source.
- [ ] `trace_data` relationship to path hashes / active traces unconfirmed (M2 spike).

---

## Cross-links

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic and this file as milestones land.
- [ ] Keep [traceroute/meshcore-path-outstanding.md](../../traceroute/meshcore-path-outstanding.md) pointed here for the active-vs-passive split.
