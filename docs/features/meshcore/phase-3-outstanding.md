# Phase 3 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 3** ([#267](https://github.com/pskillen/meshflow-api/issues/267)) — not a copy of the full epic backlog.

**Passive-path detail:** [packet-path-tracing/packet-path-tracing-outstanding.md](./packet-path-tracing/packet-path-tracing-outstanding.md).  
**Traceroute-folder mirror:** [meshcore-path-outstanding.md](../traceroute/meshcore-path-outstanding.md).

---

## MVP tiers (bot → message heard map)

Gap analysis (Jun 2026): channel **Heard** is the user-facing “map view” for MeshCore today — geo map shows sender + feeders; hop detail is **schematic** per feeder until hashes resolve to positions.

| Tier | User outcome | Tracking |
| --- | --- | --- |
| **Tier 1** | Non-empty `path_hashes` per feeder in Heard (twin + bot RAW upload) | [#385](https://github.com/pskillen/meshflow-api/issues/385) — twin hardening on `main` (observation match, content key, 120s window) |
| **Tier 2** | Hop **polylines on Leaflet** when segment rows resolve to positioned nodes | [tier-2-heard-resolution.md](./packet-path-tracing/tier-2-heard-resolution.md); auto-matcher ADR [#373](https://github.com/pskillen/meshflow-api/issues/373) still open |
| **Tier 3** | Full path tracing product (Neo4j, realtime WS, M7 topology) | [#372](https://github.com/pskillen/meshflow-api/issues/372) milestones M4–M7, [meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309) |

**Tier 1 ops:** Both feeders must run **meshflow-bot `main`** (PATH/TEXT_MSG upload) and post to API on **`main`**. If `path_hashes` stay empty, check per-feeder `RAW` row counts and twin window — not missing API merge on `main` alone.

**Recommendations**

- **Thin bot / fat server** — bot uploads additional `rx_log_data` typenames; API splits `path` and correlates to `original_mc_packet` (see [#385](https://github.com/pskillen/meshflow-api/issues/385)).
- **Deploy** precursor + M1 ([#372](https://github.com/pskillen/meshflow-api/issues/372)) in parallel; M1 rollups from ADVERT do not unblock message Heard without Tier 1.
- **Do not** invest in geo hop lines or auto-matcher heuristics before Tier 1 data lands.
- **Tier 2 shortcut:** staff manual segment annotation (M1 `PATCH …/segments/`) + `heard[]` lookup — demo map lines before safe auto-matcher ADR.

---

## Passive path

- [x] **Cross-feeder channel message dedup** — [#387](https://github.com/pskillen/meshflow-api/issues/387) on `main`.
- [ ] **Tier 1 — path twin hardening** — observation-based twin after dedup; content-key match; default 120s window ([tier-1 doc](./packet-path-tracing/tier-1-message-path-twin.md)).
- [ ] **Tier 1 — ops** — both feeders uploading `RAW` PATH/TEXT_MSG to pre-prod API.
- [ ] **Passive packet path subsystem (M1+)** — rollups, resolution table, Neo4j export, realtime/history UI ([ADR-0001](./packet-path-tracing/adr/0001-meshcore-packet-path-tracing-subsystem.md)); deploy [#378](https://github.com/pskillen/meshflow-api/pull/378) on pre-prod if not already.
- [x] **Tier 2 — `heard[]` → segment resolution table** — `bulk_format_path_hops` uses `MeshCorePathSegmentResolution` ([tier-2 doc](./packet-path-tracing/tier-2-heard-resolution.md)).
- [ ] **Proven hash → node matcher** — per [traceroute ADR §A](../traceroute/adr/0001-mc-path-hash-resolution.md); v1 uses manual/rollup rows only ([#373](https://github.com/pskillen/meshflow-api/issues/373)).
- [ ] **Tier 2 — UI MC polylines** — meshflow-ui `HeardPathGeoMap` when `resolved_path[].position` set.
- [ ] **`GET /meshcore/packets/`** — optional `resolved_path` on list/detail (deferred).

### Bot ([meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119))

Prefer **thin bot / fat server** — tracked under [#385](https://github.com/pskillen/meshflow-api/issues/385).

- [x] Upload `rx_log_data` TEXT_MSG / PATH — [bot#124](https://github.com/pskillen/meshflow-bot/pull/124) on `main`; verify per-feeder in ops.
- [ ] Unit tests for `_path_hashes()` (1/2/3-byte `path_hash_size`) when wire includes `path`.

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
- [x] **#311** — schematic hop chain per feeder in heard dialog ([meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)); blocked on Tier 1 data for production channel traffic.
