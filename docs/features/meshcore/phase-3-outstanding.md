# Phase 3 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 3** ([#267](https://github.com/pskillen/meshflow-api/issues/267)) — not a copy of the full epic backlog.

**Passive-path detail:** [packet-path-tracing/packet-path-tracing-outstanding.md](./packet-path-tracing/packet-path-tracing-outstanding.md).  
**Traceroute-folder mirror:** [meshcore-path-outstanding.md](../traceroute/meshcore-path-outstanding.md).

---

## Passive path

- [ ] **Channel text `heard[]` without hops** — `channel_message` ingest often has `path_len` but no `path`; ADVERT-only `rx_log_data` has paths but no `TextMessage` link. Server-led ingest design: [packet-path-tracing-outstanding.md § Message path data chain](./packet-path-tracing/packet-path-tracing-outstanding.md#message-path-data-chain-confirmed--pre-prod-jun-2026).
- [ ] **Passive packet path subsystem** — rollups, resolution table, Neo4j export, realtime/history UI ([ADR-0001](./packet-path-tracing/adr/0001-meshcore-packet-path-tracing-subsystem.md)).
- [ ] **Proven hash → node matcher** — per [traceroute ADR §A](../traceroute/adr/0001-mc-path-hash-resolution.md); no unsafe heuristics in v1.
- [ ] **`GET /meshcore/packets/`** — optional `resolved_path` on list/detail (deferred).
- [ ] **[meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)** — schematic hop chain per feeder in heard dialog.

### Bot ([meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119))

Prefer **thin bot / fat server** — see packet-path-tracing outstanding.

- [ ] Unit tests for `_path_hashes()` (1/2/3-byte `path_hash_size`).
- [ ] Optional: upload `rx_log_data` PATH (and related) frames for server-side `path` split.

---

## Active traceroute (epic backlog)

From [#267](https://github.com/pskillen/meshflow-api/issues/267) — not scheduled in passive slice:

- [ ] Spike + ADR: MC vs MT traceroute semantics (`meshcore_py`).
- [ ] Schema: extend `AutoTraceRoute` or add `MeshCorePathObservation`.
- [ ] `pick_traceroute_target` + Celery: never mix MT sources with MC targets.
- [ ] `traceroute_analytics` / Neo4j: protocol on nodes/edges.
- [ ] UI: heatmap / topology / coverage protocol filter.
- [ ] MC new-node baseline traceroute analog.

---

## Ops / cross-cutting

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic checklist when major slices merge.
- [ ] Keep [phase-3-progress.md](./phase-3-progress.md) in sync with [meshcore-path-progress.md](../traceroute/meshcore-path-progress.md) (avoid duplicate narratives — link, don’t fork).

---

## Resolved (do not re-open)

*(Move items here when closing.)*

- [x] **#304** — UI heard path map ([meshflow-ui#304](https://github.com/pskillen/meshflow-ui/issues/304)).
