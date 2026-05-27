# MeshCore path / traceroute parity — progress

**Epic:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267) — MeshCore Phase 3 traceroute / path parity (MC analog of Meshtastic `AutoTraceRoute` + analytics).

**Repos:** meshflow-api (primary), meshflow-bot, meshflow-ui.

**Related docs**

- Meshtastic traceroute: [README.md](README.md), [flow.md](flow.md)
- MC ingest + `path_hashes`: [packet-ingestion/meshcore.md](../packet-ingestion/meshcore.md)
- Outstanding: [meshcore-path-outstanding.md](meshcore-path-outstanding.md)

---

## Overall status

**Status:** In progress (planning + passive-path slice; active MC traceroute not started)

**Branch (docs):** `api-267/pskillen/meshcore-path-docs`

---

## Conceptual split

| Track | Goal | Status |
| --- | --- | --- |
| **Passive path** | Hop breadcrumbs on forwarded MC packets (`path_hashes` on ingest → resolve → UI) | Tickets filed; schema fix [#369](https://github.com/pskillen/meshflow-api/issues/369) pending |
| **Active traceroute** | `AutoTraceRoute` (or sibling) + bot command + scheduler + Neo4j protocol labels | Epic backlog; needs spike/ADR per #267 |

Meshtastic today: active TR drives most topology evidence; MC Phase 3 starts with **passive** evidence because the wire uses repeater hash paths, not numeric node IDs in packets.

---

## Passive path slice (2026-05-26)

**Status:** Not started (API/UI); ingest partially ready

### Bot ingest — `path_hashes` on POST body

**Status:** Core behaviour shipped (ticket still open for tests/optional PATH frames)

- [meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119) — open; `_path_hashes()` in `MeshCorePacketSerializer` when `payload.path` is present on `advert` / `channel_text` / `contact_text`.
- Production: `path_hashes` visible in DB when wire includes `path` (often null on DMs with only `path_len`).

### API storage

**Status:** Works but wrong shape for multi-feeder

- Ingest writes `path_hashes` on **`MeshCoreRawPacket`** and **`MeshCorePacketObservation`** today (`meshcore_packets/serializers.py`).
- [#369](https://github.com/pskillen/meshflow-api/issues/369) — drop raw-column; observation-only (same on-air packet, different paths per feeder).

### Resolution + read API

**Status:** Not started

- [#360](https://github.com/pskillen/meshflow-api/issues/360) — hash → `ObservedNode` (`mc_pubkey` / prefix), `resolved_path` on read APIs, ADR for ambiguity.

### UI

**Status:** Not started

- [meshflow-ui#304](https://github.com/pskillen/meshflow-ui/issues/304) — passive route display (depends on #360 + #369).

### Closed / deferred ingest scope

- [#368](https://github.com/pskillen/meshflow-api/issues/368) — bulk “all missing MC packet types” ingest **closed (not planned)**; path gaps tracked here and under #267, not #266.

---

## Documentation (this branch)

**Status:** In progress

- [packet-ingestion/meshtastic.md](../packet-ingestion/meshtastic.md) — MT ingest → business model map.
- [packet-ingestion/meshcore.md](../packet-ingestion/meshcore.md) — MC ingest map + Phase 2 vs #266 gap table.
- [packet-ingestion/README.md](../packet-ingestion/README.md) — hub updated for MC Phase 1.
- This file + [meshcore-path-outstanding.md](meshcore-path-outstanding.md).

---

## Active traceroute (epic backlog — not started)

Per [#267](https://github.com/pskillen/meshflow-api/issues/267) body:

1. Spike + ADR: MC vs MT traceroute semantics (`meshcore_py`).
2. Schema: `AutoTraceRoute.protocol` or `MeshCorePathObservation`.
3. Scheduler / Celery: never mix MT sources with MC targets.
4. `traceroute_analytics` / Neo4j protocol on edges.
5. UI heatmap/topology/coverage protocol filter.

No PRs yet.

---

## Suggested implementation order (for planning)

1. **#369** — observation-only `path_hashes` (unblocks correct multi-feeder data).
2. **#360** — resolution service + OpenAPI read shape.
3. **#304** — UI breadcrumbs.
4. **ADR spike** — active MC TR vs passive-only long term.
5. Active TR + analytics (epic items 2–5).

---

## Next

- Cursor execution plan for epic #267 (passive slice first).
- Implement #369 on `api-267/...` feature branch after docs PR merges.
