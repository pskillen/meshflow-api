# MeshCore path / traceroute parity — progress

**Epic:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267) — MeshCore Phase 3 traceroute / path parity (MC analog of Meshtastic `AutoTraceRoute` + analytics).

**Repos:** meshflow-api (primary), meshflow-bot, meshflow-ui.

**Related docs**

- Meshtastic traceroute: [README.md](README.md), [flow.md](flow.md)
- MC ingest + `path_hashes`: [packet-ingestion/meshcore.md](../packet-ingestion/meshcore.md)
- ADR (path hash v1 display): [adr/0001-mc-path-hash-resolution.md](adr/0001-mc-path-hash-resolution.md)
- Outstanding: [meshcore-path-outstanding.md](meshcore-path-outstanding.md)

---

## Overall status

**Status:** In progress (API passive-path slice on feature branch; UI/bot tests pending)

**Branch (API):** `api-267/pskillen/meshcore-path`

---

## Conceptual split

| Track | Goal | Status |
| --- | --- | --- |
| **Passive path** | Hop breadcrumbs on forwarded MC packets (`path_hashes` on ingest → display → UI map) | API #369 + #360 message slice in progress |
| **Active traceroute** | `AutoTraceRoute` (or sibling) + bot command + scheduler + Neo4j protocol labels | Epic backlog; needs spike/ADR per #267 |

Meshtastic today: active TR drives most topology evidence; MC Phase 3 starts with **passive** evidence because the wire uses repeater hash paths, not numeric node IDs in packets.

---

## Passive path slice

### Bot ingest — `path_hashes` on POST body

**Status:** Core behaviour shipped (tests in meshflow-bot PR)

- [meshflow-bot#119](https://github.com/pskillen/meshflow-bot/issues/119) — `_path_hashes()` when wire `path` present.

### API storage ([#369](https://github.com/pskillen/meshflow-api/issues/369))

**Status:** Done on `api-267/pskillen/meshcore-path`

- `path_hashes` on **`MeshCorePacketObservation` only**; dropped from `MeshCoreRawPacket`.
- Ingest uses `update_or_create` on `(packet, observer)` to refresh path/RF fields.

### Message API ([#360](https://github.com/pskillen/meshflow-api/issues/360) narrowed)

**Status:** Done on feature branch (message history only)

- `GET /api/messages/text/` — `sender_position`, MT `heard[].observer_position`, MC `heard[]` with `path_hashes`, `resolved_path` (v1 `status=unknown`), `path_known=false`.
- Prefetch + bulk hop cache; no `resolved_path` on packet list API.
- ADR: [0001-mc-path-hash-resolution.md](adr/0001-mc-path-hash-resolution.md) — hash→node linking **unproven**; matcher deferred.

### UI ([#304](https://github.com/pskillen/meshflow-ui/issues/304))

**Status:** Done (2026-05-27) — follow-up **[meshflow-ui#311](https://github.com/pskillen/meshflow-ui/issues/311)** for logical hop layout per feeder

- `HeardPathMap` + heard dialog (MT + MC); v1 shows feeders geo + minimal dashed paths.
- #311: schematic hop chain per observer, path detail beside each feeder row (not geographic hops).

---

## Documentation

- [packet-ingestion/meshtastic.md](../packet-ingestion/meshtastic.md), [meshcore.md](../packet-ingestion/meshcore.md)
- This file + [meshcore-path-outstanding.md](meshcore-path-outstanding.md)
- [adr/0001-mc-path-hash-resolution.md](adr/0001-mc-path-hash-resolution.md)

---

## Active traceroute (epic backlog — not started)

Per [#267](https://github.com/pskillen/meshflow-api/issues/267) body — no PRs yet.

---

## Next

1. Merge API PR (closes #369, #360 message slice).
2. UI PR `ui-267/pskillen/meshcore-path` (closes meshflow-ui#304).
3. Bot unit tests PR for `_path_hashes()`.
4. Proven hash→`ObservedNode` matcher after upstream spec (ADR §A follow-up).
