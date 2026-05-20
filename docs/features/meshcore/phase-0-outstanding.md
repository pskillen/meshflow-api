# Phase 0 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 0 execution** — not a copy of the [#264](https://github.com/pskillen/meshflow-api/issues/264) epic checklist.

---

## meshflow-bot

- [ ] **Unit coverage of live Meshtastic adapter paths** — `src/meshtastic/radio.py` (and TCP/pubsub) remain primarily smoke/integration; omitted from coverage denominator by design; no dedicated unit suite under the 70% gate.
- [ ] **MeshCore TCP transport** — `MeshCore.create_tcp` not wired in `main.py` (serial + BLE only).
- [ ] **Dedicated per-`EventType` subscriber files** — implementation uses one wildcard subscriber; do not expect per-event handler modules.
- [ ] **Epic #264 cleanup (ops / packaging)** — confirm child issues still open on your deployment:
  - [#270](https://github.com/pskillen/meshflow-api/issues/270) repo rename tidy (bot + ui docs/CI/metadata)
  - meshflow-bot [#81](https://github.com/pskillen/meshflow-bot/issues/81) remove legacy Docker tag after volunteer migration
  - meshflow-bot [#84](https://github.com/pskillen/meshflow-bot/issues/84) / [#80](https://github.com/pskillen/meshflow-bot/issues/80) — verify published image tags match current `ghcr.io/pskillen/meshflow-bot` naming

---

## meshflow-api / meshflow-ui

- [ ] None required for Phase 0 application code (0.5 was docs-only).

---

## Resolved (do not re-open)

- [x] MeshCore runtime adapter + `RADIO_PROTOCOL=meshcore` — Phase 0.3.
- [x] Capture bundle + bot field doc — Phase 0.4.
- [x] API ADRs + trimmed samples — Phase 0.5 / PR #289.
