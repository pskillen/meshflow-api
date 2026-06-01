# MeshCore path / traceroute parity — outstanding

Items **skipped**, **incomplete**, or **discovered during planning** for [#267](https://github.com/pskillen/meshflow-api/issues/267).

---

## Passive path

- [x] **#369** — observation-only `path_hashes` (API branch `api-267/pskillen/meshcore-path`).
- [x] **#360 (narrowed)** — message `heard[]` path display + positions (not packet list API).
- [ ] **Passive packet path subsystem** — proposed in [meshcore/packet-path-tracing ADR-0001](../meshcore/packet-path-tracing/adr/0001-meshcore-packet-path-tracing-subsystem.md): passive edge rollups, resolution table, Neo4j export, realtime/history UI. Progress/outstanding now tracked under [packet-path-tracing/](../meshcore/packet-path-tracing/packet-path-tracing-progress.md).
- [ ] **Proven matcher** — implement hash segment → `ObservedNode` when [ADR §A](adr/0001-mc-path-hash-resolution.md) documents safe rules (no `iendswith` / `last_heard` heuristics in v1).
- [ ] **`GET /meshcore/packets/`** — optional `resolved_path` on packet list/detail (deferred).
- [x] **#304** — UI `HeardPathMap` + heard dialog (meshflow-ui, closed 2026-05-27).
- [ ] **[meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)** — HeardPathMap logical path per feeder (follow-up to #304): schematic hop chain, feeder list with path beside each row; not geographic hop placement.

---

## Bot ([meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119))

- [ ] Unit tests for `_path_hashes()` (1/2/3-byte `path_hash_size`) — separate bot PR.
- [ ] Optional: upload `rx_log_data` PATH-only frames.
- [ ] Document limitation: `path_len > 0` but no `path` on decoded messages → `path_hashes` often null.

---

## Active traceroute (deferred)

- [ ] Spike / ADR: MC active trace vs Meshtastic `TRACEROUTE_APP`.
- [ ] `pick_traceroute_target` protocol guard.
- [ ] Neo4j / heatmap protocol dimension.
- [ ] MC new-node baseline traceroute analog.

---

## Cross-links

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic when API PR merges.
- [ ] Optional: `flow.md` section “MeshCore passive path” once UI lands.
