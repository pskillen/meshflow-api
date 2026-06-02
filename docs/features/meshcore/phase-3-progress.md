# Phase 3 — progress

**Epic:** [#267](https://github.com/pskillen/meshflow-api/issues/267) — MeshCore traceroute / path parity (planning + passive path first).

**Milestone:** MeshCore Support.

---

## Scope (epic summary)

MC **path/trace** or passive hop accumulation as a Meshtastic traceroute analog: `AutoTraceRoute.protocol` (or sibling model), scheduler guards by protocol, Neo4j edges labelled by protocol, UI filters on traceroute pages, MC new-node baseline.

**Two tracks** (see [traceroute/meshcore-path-progress.md](../traceroute/meshcore-path-progress.md)):

| Track | Goal | Detail doc |
| --- | --- | --- |
| **Passive path** | `path_hashes` on observations → resolve → UI / rollups | [packet-path-tracing/packet-path-tracing-progress.md](./packet-path-tracing/packet-path-tracing-progress.md) |
| **Active traceroute** | Bot command + `AutoTraceRoute` (or MC sibling) + analytics | *Not started — spike/ADR backlog* |

---

## Delivered (log here as work lands)

*(Stub — add sections with PR/issue links when closing slices.)*

### Passive path — message heard UI

- [meshflow-ui#304](https://github.com/pskillen/meshflow-ui/issues/304) — heard path map in message UI (closed 2026-05-27).

### Passive path — API `path_hashes` on observations

- See [meshcore-path-progress.md](../traceroute/meshcore-path-progress.md) § Passive path slice ([#369](https://github.com/pskillen/meshflow-api/issues/369), [#360](https://github.com/pskillen/meshflow-api/issues/360)).

### Passive path — bot forward `path` when present

- [meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119) — `_path_hashes()` on ingest when wire `path` is set.

---

### Passive path — heard UI per-feeder schematic

- [meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311) — `MeshCoreHeardPathsPanel` / `PathHopChain` per feeder in heard dialog.

---

## In flight

- **Tier 1 MVP (message heard paths)** — [#385](https://github.com/pskillen/meshflow-api/issues/385): bot uploads TEXT_MSG/PATH as `raw`; API `path_twin` merges onto `channel_text` observations. Design: [tier-1-message-path-twin.md](./packet-path-tracing/tier-1-message-path-twin.md).
- **Packet path subsystem (M1)** — ADR + rollups + staff segments API: [packet-path-tracing/](./packet-path-tracing/); PRs [#378](https://github.com/pskillen/meshflow-api/pull/378), [bot#122](https://github.com/pskillen/meshflow-bot/pull/122), [ui#310](https://github.com/pskillen/meshflow-ui/pull/310).

---

## Cross-repo issue map (passive slice)

| Repo | Issue |
| --- | --- |
| meshflow-api | [#360](https://github.com/pskillen/meshflow-api/issues/360), [#369](https://github.com/pskillen/meshflow-api/issues/369), **[#385](https://github.com/pskillen/meshflow-api/issues/385)** (Tier 1), [#372](https://github.com/pskillen/meshflow-api/issues/372) (M1) |
| meshflow-bot | [#119](https://github.com/pskillen/meshflow-bot/issues/119) (+ [#385](https://github.com/pskillen/meshflow-api/issues/385) upload surface) |
| meshflow-ui | [#304](https://github.com/pskillen/meshflow-ui/issues/304), [#311](https://github.com/pskillen/meshflow-ui/issues/311) |

---

## References

- [phase-3-outstanding.md](./phase-3-outstanding.md) — MVP tiers (Tier 1 [#385](https://github.com/pskillen/meshflow-api/issues/385))
- [traceroute/README.md](../traceroute/README.md) § MeshCore path parity
- [ADR-0001 — MC path hash resolution](../traceroute/adr/0001-mc-path-hash-resolution.md)
- [packet-ingestion/meshcore.md](../packet-ingestion/meshcore.md) — what the bot uploads today
