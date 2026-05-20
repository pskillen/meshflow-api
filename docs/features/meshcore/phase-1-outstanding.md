# Phase 1 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 1 execution** — not the full [#265](https://github.com/pskillen/meshflow-api/issues/265) backlog (Phase 2 owns most follow-ons).

---

## Deferred at Phase 1 close (explicitly out of MVP)

- [ ] **`TextMessage` normalisation for MeshCore** — no `meshcore_text_packet_received` pipeline yet (Phase 2.2 / [#296](https://github.com/pskillen/meshflow-api/issues/296)).
- [ ] **Telemetry / ack / req / resp packet subclasses** — storage-only types not landed.
- [ ] **Meshtastic UI pages showing MeshCore rows** — minimal MC-only surfaces shipped; mixed MT pages unchanged.
- [ ] **Automated 24h ingest acceptance gate** — operator checklist in [feeder-bootstrap.md](./feeder-bootstrap.md); nightly automation not wired.

---

## Discovered gaps (not in original MVP plan text)

- [ ] **Shared constellation API key on MC ingest** — Meshtastic disambiguates via URL `{node_id}`; MC ingest has no feeder identity in body yet → **one key per MC feeder** until feeder pubkey (or similar) is on the wire ([feeder-bootstrap.md](./feeder-bootstrap.md)).
- [ ] **Optional bot display alignment** — local `mc:` id vs API computed `node_id_str` ([#83](https://github.com/pskillen/meshflow-bot/issues/83) follow-up).
- [ ] **Neo4j / analytics `protocol` on edges** — left as module TODOs; traceroute Phase 3.

---

## Phase 1.0 / 1.x — closed deferrals

- [x] MeshCore identity columns + `meshcore_packets` app — shipped in Phase 1 (was listed as post-1.0 in 1.0 “not done” notes).
- [x] Drop stored `ObservedNode.node_id_str` — [#294](https://github.com/pskillen/meshflow-api/issues/294) / PR #326.
- [x] Rename API field to `display_id` — explicitly out of scope; JSON stays `node_id_str`.

---

## Production / ops (handoff to Phase 2)

- [ ] **Map GPS for all feeders** — required **Phase 2.1** bot + api deploy ([#298](https://github.com/pskillen/meshflow-api/issues/298)); see [phase-2-outstanding.md](./phase-2-outstanding.md) for deploy/SQL verification.
