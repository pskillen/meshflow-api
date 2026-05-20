# Phase 0 — progress

**Epic:** [#264](https://github.com/pskillen/meshflow-api/issues/264) — bot refactor, MeshCore exploration, ADRs.  
**Repos:** primarily **meshflow-bot**; **meshflow-api** docs only from 0.5 onward.

---

## Phase 0 — Bot protocol seam (`RadioInterface`, Meshtastic adapter)

**Status:** Complete. **Tracking:** meshflow-bot [#80](https://github.com/pskillen/meshflow-bot/issues/80), [PR #87](https://github.com/pskillen/meshflow-bot/pull/87).

**meshflow-bot — delivered**

- `RadioInterface` + `RadioHandlers` (`src/radio/interface.py`); domain events (`src/radio/events.py`); error boundaries (`src/radio/errors.py`).
- `MeshflowBot` (`src/bot.py`); `MeshtasticBot` alias; Meshtastic package under `src/meshtastic/`.
- `src/main.py`: `RADIO_PROTOCOL` (default `meshtastic`) → `MeshtasticRadio`.
- Tests: `FakeRadio`, translation/serializer tests, `test_bot_integration.py`; coverage gate ≥70% (`pyproject.toml` with documented omits).
- CI: `.github/workflows/unit-tests.yaml` + `requirements.dev.txt`.

**meshflow-api / meshflow-ui:** no application changes for this sub-phase.

---

## Phase 0.3 — MeshCore capture-only connectivity

**Status:** Complete. **Tracking:** meshflow-bot [PR #88](https://github.com/pskillen/meshflow-bot/pull/88).

**meshflow-bot — delivered**

- `meshcore>=2.3.7,<3.0.0`; package `src/meshcore/` (`radio.py`, `translation.py`, `dump.py`, `serializers.py` stub).
- `RADIO_PROTOCOL=meshcore` + serial/BLE env; JSON dumps under `{data_dir}/meshcore_packets/`; no `StorageAPIWrapper` / WS.
- `send_*` raises `RadioError`; `MeshCorePacketSerializer` stub (`NotImplementedError`).
- Docker: `meshflow-bot-meshtastic` + `meshflow-bot-meshcore` compose services.
- Docs: `docs/MESHCORE.md`, `docs/MESHTASTIC.md`; tests under `test/meshcore/`.

**meshflow-api / meshflow-ui:** no code changes (api index doc updated separately).

---

## Phase 0.4 — Capture campaign + field docs (bot)

**Status:** Complete. **Tracking:** [#275](https://github.com/pskillen/meshflow-api/issues/275), bot [PR #89](https://github.com/pskillen/meshflow-bot/pull/89).

**meshflow-bot — delivered**

- Committed tree `docs/meshcore_packets/` + `meshcore_packets_20260512.tar.gz`.
- `docs/meshcore_packets/README.md` (ops, inventory, representative samples).
- `docs/meshcore_packets/MESHCORE_PACKET_FIELDS.md` (capture-verified tables + explicit gaps).
- `docs/MESHCORE.md` updated (0.4 complete, pointers to 0.5 / 1.x).

**meshflow-api:** API mirror deferred to Phase 0.5 (not in bot PR #89).

---

## Phase 0.5 — ADRs + API evidence bundle

**Status:** Complete (documentation only). **Tracking:** [#276](https://github.com/pskillen/meshflow-api/issues/276), [PR #289](https://github.com/pskillen/meshflow-api/pull/289).

**meshflow-api — delivered**

- `docs/features/packet-ingestion/MESHCORE_PACKET_FIELDS.md`
- `docs/packets/meshcore/` — README + one JSON per visible shape
- `docs/features/packet-ingestion/adr/` — `0001`–`0004` (identity, channels, broadcast, dedup) + index
- `docs/features/packet-ingestion/README.md` — MeshCore Phase 0.5 subsection

**meshflow-bot / meshflow-ui:** no changes; full capture bundle remains on bot `docs/meshcore_packets/`.

---

## Verification (Phase 0)

1. **Meshtastic:** `RADIO_PROTOCOL=meshtastic` (or unset) — behaviour matches post–Phase 0 smoke.
2. **MeshCore capture:** `RADIO_PROTOCOL=meshcore` + device env — dumps under `data/meshcore_packets/`; no ingest HTTP.
3. **Bot tests:** `pytest test/ --doctest-modules` — green, ≥70% coverage.
4. **API ADRs:** PR #289 paths on `main`; spot-check Evidence vs `docs/packets/meshcore/*.json`.
