# Phase 3 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 3** ([#267](https://github.com/pskillen/meshflow-api/issues/267)) — not a copy of the full epic backlog.

**Passive-path detail:** [packet-path-tracing/packet-path-tracing-outstanding.md](./packet-path-tracing/packet-path-tracing-outstanding.md).  
**Traceroute-folder mirror:** [meshcore-path-outstanding.md](../traceroute/meshcore-path-outstanding.md).

---

## MVP tiers (bot → message heard map)

Gap analysis (Jun 2026): channel **Heard** is the user-facing “map view” for MeshCore today — geo map shows sender + feeders; hop detail is **schematic** per feeder until hashes resolve to positions.

| Tier | User outcome | Tracking |
| --- | --- | --- |
| **Tier 1** (ship next) | Real `#channel` messages show **non-empty `path_hashes`** in Heard (unknown hop labels OK) | **[#385](https://github.com/pskillen/meshflow-api/issues/385)** |
| **Tier 2** | Hop **polylines on Leaflet** when hashes map to node positions | M2/M3 matcher ([#373](https://github.com/pskillen/meshflow-api/issues/373), [#374](https://github.com/pskillen/meshflow-api/issues/374)); wire `heard[]` to M1 `MeshCorePathSegmentResolution`; UI draw MC waypoints with `position` |
| **Tier 3** | Full path tracing product (Neo4j, realtime WS, M7 topology) | [#372](https://github.com/pskillen/meshflow-api/issues/372) milestones M4–M7, [meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309) |

**Tier 1 blocker (pre-prod):** `channel_text` linked to `TextMessage` has empty `path_hashes`; PATH/TEXT_MSG `rx_log_data` with `path` is not uploaded. Precursor + UI ([#369](https://github.com/pskillen/meshflow-api/issues/369), [#304](https://github.com/pskillen/meshflow-ui/issues/304), [#311](https://github.com/pskillen/meshflow-ui/issues/311)) already work when data exists — **no new UI for Tier 1**.

**Recommendations**

- **Thin bot / fat server** — bot uploads additional `rx_log_data` typenames; API splits `path` and correlates to `original_mc_packet` (see [#385](https://github.com/pskillen/meshflow-api/issues/385)).
- **Deploy** precursor + M1 ([#372](https://github.com/pskillen/meshflow-api/issues/372)) in parallel; M1 rollups from ADVERT do not unblock message Heard without Tier 1.
- **Do not** invest in geo hop lines or auto-matcher heuristics before Tier 1 data lands.
- **Tier 2 shortcut:** staff manual segment annotation (M1 `PATCH …/segments/`) + `heard[]` lookup — demo map lines before safe auto-matcher ADR.

---

## Passive path

- [ ] **Tier 1 — message path data chain** — [#385](https://github.com/pskillen/meshflow-api/issues/385): `path_hashes` on observation tied to `TextMessage.original_mc_packet` for channel traffic. Detail: [packet-path-tracing-outstanding.md § Message path data chain](./packet-path-tracing/packet-path-tracing-outstanding.md#message-path-data-chain-confirmed--pre-prod-jun-2026).
- [ ] **Passive packet path subsystem (M1+)** — rollups, resolution table, Neo4j export, realtime/history UI ([ADR-0001](./packet-path-tracing/adr/0001-meshcore-packet-path-tracing-subsystem.md)); merge/deploy PRs [#378](https://github.com/pskillen/meshflow-api/pull/378), [bot#122](https://github.com/pskillen/meshflow-bot/pull/122), [ui#310](https://github.com/pskillen/meshflow-ui/pull/310).
- [ ] **Tier 2 — `heard[]` → segment resolution table** — augment `bulk_format_path_hops` in `text_messages/views.py` with `MeshCorePathSegmentResolution` (manual + resolved rows).
- [ ] **Proven hash → node matcher** — per [traceroute ADR §A](../traceroute/adr/0001-mc-path-hash-resolution.md); no unsafe heuristics in v1 ([#373](https://github.com/pskillen/meshflow-api/issues/373)).
- [ ] **`GET /meshcore/packets/`** — optional `resolved_path` on list/detail (deferred).

### Bot ([meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119))

Prefer **thin bot / fat server** — tracked under [#385](https://github.com/pskillen/meshflow-api/issues/385).

- [ ] Upload `rx_log_data` TEXT_MSG / PATH (or raw pass-through) — **required for Tier 1**; no bot-side correlation.
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
