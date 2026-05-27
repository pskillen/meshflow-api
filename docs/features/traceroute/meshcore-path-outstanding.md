# MeshCore path / traceroute parity — outstanding

Items **skipped**, **incomplete**, or **discovered during planning** for [#267](https://github.com/pskillen/meshflow-api/issues/267) — not the full epic backlog (see epic issue + [meshcore-path-progress.md](meshcore-path-progress.md)).

---

## Passive path — schema & ingest

- [ ] **#369** — remove `path_hashes` from `meshcore_packets_raw`; observation-only; no prod backfill.
- [ ] **`_ensure_observation`** — on dedup re-ingest, update observation RF/path fields when observer already has a row (verify `get_or_create` behaviour).
- [ ] **#360** — ADR: hash segment → `ObservedNode` (collisions, unknown hops).
- [ ] **#360** — read API `resolved_path` (or nested observations on packet detail).
- [ ] **#304** — UI passive path (meshflow-ui).

---

## Bot ([meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119))

- [ ] Unit tests for `_path_hashes()` (1/2/3-byte `path_hash_size`) — core forward behaviour already in production.
- [ ] Optional: upload `rx_log_data` PATH-only frames (coordinate API payload type if added).
- [ ] Document limitation: `path_len > 0` but no `path` on decoded `channel_message` / `contact_message` → `path_hashes` often null.

---

## Active traceroute (deferred)

- [ ] Spike / ADR: MC active trace vs Meshtastic `TRACEROUTE_APP` + `AutoTraceRoute` lifecycle.
- [ ] `pick_traceroute_target` protocol guard (MT feeder → MT target only).
- [ ] Neo4j / heatmap protocol dimension on edges.
- [ ] MC new-node baseline traceroute analog (if distinct from passive path evidence).

---

## Cross-links / doc drift

- [ ] Update [#267](https://github.com/pskillen/meshflow-api/issues/267) epic body table when #369 lands (observation-only note).
- [ ] [#360](https://github.com/pskillen/meshflow-api/issues/360) issue text still says path on `MeshCoreRawPacket` — refresh after #369.
- [ ] Optional: `flow.md` section “MeshCore passive path” once read API is stable.
