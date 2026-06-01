# MeshCore passive packet path — progress

**Tracking:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267) (MeshCore Phase 3 path parity epic)
**Plan:** Cursor plan `MC passive path M1` (detailed M1) + `MC packet path milestones` (overview) + [ADR-0001](adr/0001-meshcore-packet-path-tracing-subsystem.md)
**Repos:** meshflow-api (primary), meshflow-bot, meshflow-ui

---

## Overall status

**Status:** In progress

**Branch:** `api-372/pskillen/meshcore-passive-path-m1` (meshflow-api, meshflow-bot, meshflow-ui)

The display-only passive slice that precedes this subsystem has **shipped** (see Precursor below). M1 implementation in flight (capture, `meshcore_packet_path` app, rollup/eviction, edges/segments API, diagnostic UI).

**Locked decisions (ADR-0001 open questions):**

- App name: `meshcore_packet_path`.
- Neo4j: new `PATH_OBSERVED` relationship type (separate from `ROUTED_TO`).
- Retention: 6 months; every persisting milestone ships a Celery eviction job.
- Open until M2 spike: meaning of `path_hash_mode`; centrality in Postgres vs Neo4j.

---

## Precursor — display-only passive slice (shipped)

**Status:** Complete

| Issue | Repo | Delivered |
| --- | --- | --- |
| [#369](https://github.com/pskillen/meshflow-api/issues/369) | api | `path_hashes` moved to `MeshCorePacketObservation` only; `update_or_create` per `(packet, observer)` |
| [#360](https://github.com/pskillen/meshflow-api/issues/360) | api | Message `heard[]` exposes `path_hashes`, display-only `resolved_path` (`status=unknown`), `path_known=false` |
| [#119](https://github.com/pskillen/meshflow-bot/issues/119) | bot | `_path_hashes()` forwards segments on ingest |
| [#304](https://github.com/pskillen/meshflow-ui/issues/304) | ui | `HeardPathMap` + heard dialog renders hops/feeders |

These provide the raw capture (`MeshCorePacketObservation.path_hashes`) and read-time formatter (`meshcore_packets/services/path_resolution.py`) the new subsystem builds on.

---

## Milestones

Tracked as sub-issues of [#267](https://github.com/pskillen/meshflow-api/issues/267); see [ADR-0001](adr/0001-meshcore-packet-path-tracing-subsystem.md) for scope. This file records what ships; do not duplicate milestone detail here.

| Milestone | Issue | Status |
| --- | --- | --- |
| M1 MVP (capture + resolution table + hourly rollup + eviction + edges/segments API + diagnostic UI) | [#372](https://github.com/pskillen/meshflow-api/issues/372) | In progress |
| M2 resolution spike (decision gate) | [#373](https://github.com/pskillen/meshflow-api/issues/373) | Not started |
| M3 proactive resolver (conditional on M2) | [#374](https://github.com/pskillen/meshflow-api/issues/374) | Not started |
| M4 Neo4j `PATH_OBSERVED` export | [#375](https://github.com/pskillen/meshflow-api/issues/375) | Not started |
| M5 realtime WS + recent API | [#376](https://github.com/pskillen/meshflow-api/issues/376) | Not started |
| M6 history / centrality API | [#377](https://github.com/pskillen/meshflow-api/issues/377) | Not started |
| M7 UI realtime + history/topology | [meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309) | Not started |

**M1 scope note.** M1 was expanded to also ship a read/annotate API (`/meshcore/path-tracing/segments/` with staff manual annotation) and a **diagnostic UI MVP** (data tables, not the M7 map) so the user has enough visibility into captured passive data to make informed M2 decisions. M1 therefore spans all three repos. The full topology/realtime UI remains M7 (meshflow-ui#309).

---

## Next

- Execute M1 per the detailed Cursor plan `MC passive path M1`.
- Branch from latest `origin/main` as `api-372/pskillen/meshcore-passive-path-m1` in meshflow-api, meshflow-bot, and meshflow-ui; atomic conventional commits; PRs via github-personal MCP.
