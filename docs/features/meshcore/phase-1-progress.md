# Phase 1 — progress

**Epic:** [#265](https://github.com/pskillen/meshflow-api/issues/265) — MC ingestion MVP.  
**Repos:** meshflow-api, meshflow-bot, meshflow-ui.

---

## Phase 1.0 — Protocol prep + Meshtastic relabelling (api only)

**Status:** Complete. **Tracking:** [#290](https://github.com/pskillen/meshflow-api/issues/290), [PR #291](https://github.com/pskillen/meshflow-api/pull/291), [PR #292](https://github.com/pskillen/meshflow-api/pull/292).

**Delivered**

- `Meshflow/common/protocol.py` — `Protocol` enum; nullable `ObservedNode.node_id` + CHECK; `protocol` / `mc_channel_idx` on shared models.
- `MESHTASTIC_BROADCAST_ID`; Meshtastic ingest URL names + OpenAPI **Meshtastic packets** tag; `MeshProtocol` schema.
- `RawPacket` → **`MtRawPacket`**, table `packets_mt_raw_packet`, migration `packets.0017` + `migration_operations.py`; admin + cross-app renames.
- Migrations: `nodes/0034`, `constellations/0006`; tests + packet-ingestion doc updates.

**meshflow-bot / meshflow-ui:** no changes in 1.0.

---

## Phase 1 — MeshCore ingestion MVP

**Status:** Complete (implementation). **Tracking:** epic [#265](https://github.com/pskillen/meshflow-api/issues/265).

**meshflow-api**

- `ObservedNode.mc_pubkey` / `mc_pubkey_prefix`, CHECK + partial unique ([#279](https://github.com/pskillen/meshflow-api/issues/279)).
- `meshcore_packets` app — ingest, list, dedup, `ObservedNode` receiver ([#280](https://github.com/pskillen/meshflow-api/issues/280), [#278](https://github.com/pskillen/meshflow-api/issues/278)).
- Observed-nodes `protocol` filter ([#284](https://github.com/pskillen/meshflow-api/issues/284)).
- `openapi.yaml`, `docs/ENV_VARS.md`, [feeder-bootstrap.md](./feeder-bootstrap.md).

**meshflow-bot**

- `MeshCorePacketSerializer`, `store_raw_meshcore_packet`, `MESHCORE_UPLOAD_ENABLED` ([#83](https://github.com/pskillen/meshflow-bot/issues/83)).

**meshflow-ui**

- MeshCore map + nodes list, sidebar, API hooks ([#250](https://github.com/pskillen/meshflow-ui/issues/250)).

---

## Phase 1.x — Computed `ObservedNode.node_id_str` (api only)

**Status:** Complete. **Tracking:** [#294](https://github.com/pskillen/meshflow-api/issues/294), [PR #326](https://github.com/pskillen/meshflow-api/pull/326).

**Delivered**

- Removed stored `node_id_str` column; `@property` via `observed_node_id_str()`; migrations `0043`–`0044`.
- Search via `observed_node_search_conditions()`; serializers/ingest/admin/stats updated; tests + OpenAPI read-only note.
- ADR-0001 §6 deferral closed; [feeder-bootstrap.md](./feeder-bootstrap.md) SQL notes updated.

**meshflow-bot / meshflow-ui:** JSON key `node_id_str` unchanged for clients.

---

## Verification (Phase 1)

1. `python -m pytest Meshflow/meshcore_packets/tests/ Meshflow/common/tests/test_meshcore_node_helpers.py -v`
2. Phase 1.x: `Meshflow/common/tests/test_observed_node_id_str.py` + search tests; full `pytest Meshflow/ -v` before merge.
3. Bot: `pytest test/meshcore/ -v`
4. UI: `npm run build`
5. Integration: `MESHFLOW_MC_API_KEY=... pytest tests/integration/test_meshcore_ingest.py -v`
