# Phase 2 — progress

**Epic:** [#266](https://github.com/pskillen/meshflow-api/issues/266) — full MC packet types & UI parity.  
**Rename sub-epic:** [#307](https://github.com/pskillen/meshflow-api/issues/307) (SP-01–SP-11).

---

## Phase 2 — MC position from ADVERT ingest (api)

**Status:** Complete (API position pipeline). **Tracking:** [#298](https://github.com/pskillen/meshflow-api/issues/298), [PR #328](https://github.com/pskillen/meshflow-api/pull/328) (merged).

**Delivered**

- `MeshCoreLocationSource` + nullable `meshcore_location_source` on `Position` / `NodeLatestStatus` (internal).
- `Position.original_mc_packet` FK; migration `nodes.0045`.
- `meshcore_packets/services/position.py` — `apply_advert_position`; receiver + tests (`test_advert_position.py`).

**Note:** End-to-end map GPS also needs Phase 2.1 bot upload (below).

---

## Phase 2.1 — `rx_log_data` ADVERT pipeline (api + bot)

**Status:** Complete (implementation). **Tracking:** api [#330](https://github.com/pskillen/meshflow-api/issues/330), bot [#102](https://github.com/pskillen/meshflow-bot/issues/102).

**Problem addressed:** Production feeders had `advertisement` only; GPS is on wire as `rx_log_data` + `payload_typename: ADVERT` (`adv_lat`/`adv_lon`/`adv_key`).

**meshflow-api — delivered** ([PR #331](https://github.com/pskillen/meshflow-api/pull/331))

- `advert_fields.py` — nested `raw.payload` resolution; receiver uses `adv_key` when `from_pubkey` empty.
- Tests + integration round-trip; `openapi.yaml` + packet-ingestion README.

**meshflow-bot — delivered** ([PR #103](https://github.com/pskillen/meshflow-bot/pull/103))

- `EventType.RX_LOG_DATA` → `IncomingPacket`; translation tests; `docs/MESHCORE.md` upload table.

**meshflow-ui:** no changes (map reads NLS lat/lon when present).

**Deploy order:** api #331 → bot #103 on feeders with `MESHCORE_UPLOAD_ENABLED=true`.

---

## Rename track (SP-01–SP-11) — Meshtastic labelling & API contract

**Status:** In progress (2026-05-19). **SP-01–SP-04** on `main`; **SP-05** skipped; **SP-06–SP-11** on open PRs.

| ID | Scope | Status | PRs |
| --- | --- | --- | --- |
| SP-01 | OpenAPI contract alignment | **merged** | api [#320](https://github.com/pskillen/meshflow-api/pull/320) |
| SP-02 | Comment / help_text labelling | **merged** | [#321](https://github.com/pskillen/meshflow-api/pull/321), [bot#96](https://github.com/pskillen/meshflow-bot/pull/96), [ui#267](https://github.com/pskillen/meshflow-ui/pull/267) |
| SP-03 | `node_id` → `meshtastic_node_id` | **merged** | [#322](https://github.com/pskillen/meshflow-api/pull/322), [ui#268](https://github.com/pskillen/meshflow-ui/pull/268) |
| SP-04 | ObservedNode `meshtastic_*` identity | **merged** | [#323](https://github.com/pskillen/meshflow-api/pull/323), [ui#270](https://github.com/pskillen/meshflow-ui/pull/270) |
| SP-05 | MtRawPacket wire renames | **skipped** | [#311](https://github.com/pskillen/meshflow-api/issues/311) |
| SP-06 | `meshtastic_channel_0..7`, constellation bot defaults | PR open | [#324](https://github.com/pskillen/meshflow-api/pull/324), [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-07 | TextMessage MT field renames | PR open | same batch |
| SP-08 | Metrics `meshtastic_*` columns | PR open | same batch |
| SP-09 | UI `MeshflowApi` / `useMeshflowApi` | PR open | [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-10 | Bot local naming | PR open | [bot#98](https://github.com/pskillen/meshflow-bot/pull/98) |
| SP-11 | Observed-node lookup by `internal_id` | PR open | [#324](https://github.com/pskillen/meshflow-api/pull/324), [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |

**Batch branch:** api + ui `api-307/pskillen/meshcore-rename-sp06-sp11`; bot SP-10 `api-317/pskillen/meshcore-rename-sp10-bot-local`.

**Cumulative on `main` (rename + related):** OpenAPI Meshtastic paths/tags; migrations `nodes/0037`–`0039` merged; Phase 1.x `0043`–`0044` (`node_id_str` drop) after rename `0040`–`0041` on batch branch.

Sub-plan detail: `IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md`.

---

## Parallel: bot version reporting ([#99](https://github.com/pskillen/meshflow-bot/issues/99))

**Status:** PRs open (not part of #307).

| Repo | PR |
| --- | --- |
| meshflow-api | [#325](https://github.com/pskillen/meshflow-api/pull/325) — `PUT …/bot-version/`, `nodes/0042` |
| meshflow-bot | [#100](https://github.com/pskillen/meshflow-bot/pull/100) |
| meshflow-ui | [#272](https://github.com/pskillen/meshflow-ui/pull/272) |

Deploy api #325 before bot fleet upgrade.

---

## Phase 2.2 — text messages & channels

**Status:** Implemented on branch `api-296/paddy/mc-text-channels` (API + bot + ui); PRs pending. **Guide:** [text-message-channels.md](./text-message-channels.md). **Issues:** [#296](https://github.com/pskillen/meshflow-api/issues/296), [#297](https://github.com/pskillen/meshflow-api/issues/297).

**meshflow-api — delivered**

- `MessageChannel.mc_channel_type` / `mc_hashtag`; `ManagedNode.mc_channels` M2M + `mc_channels_synced_at`.
- `POST /api/meshcore/feeder/mc-channel-sync/`; `POST …/apply-mc-channel-config/` (WS dispatch).
- `MeshCoreTextMessageService` + `text_messages` receiver; `TextMessage.protocol` + `original_mc_packet`.
- History API `protocol` query; MC `heard` from `MeshCorePacketObservation`.
- `managed_node_ws_group` for MC feeder WebSocket (`node_mc_{internal_id}`).
- Tests: `test_channel_sync.py`, `test_text_message_service.py`.

**meshflow-bot — delivered**

- `read_device_channels` / `apply_device_channels` via meshcore_py; `post_mc_channel_sync` on connect.
- WS `apply_mc_channel_config`; MC feeders enable WebSocket when storage API configured.

**meshflow-ui — delivered**

- MeshCore channel panel on Node Settings (mirror + apply-to-radio).

---

## Verification

**Position / ingest**

1. `python -m pytest Meshflow/meshcore_packets/tests/ -v`
2. `python manage.py migrate` (`nodes.0045`+)

**Production E2E (after api #331 + bot #103 deploy)**

```sql
SELECT event_type, COUNT(*) FROM meshcore_packets_raw GROUP BY event_type;
SELECT COUNT(*) FROM nodes_nodelateststatus nls
  JOIN nodes_observednode n ON n.internal_id = nls.node_id
  WHERE n.protocol = 2 AND nls.latitude IS NOT NULL;
```

Expect `rx_log_data` in the first query and growing MC NLS with lat/lon in the second.

**Rename batch (after #324 merge)**

1. `python -m pytest Meshflow/ -v` on `main` with #320–#323.
2. Migrate through `nodes.0041`, `constellations/0008`, `text_messages/0007`, `packets/0018`.
3. `pytest tests/integration/ -v` with `seed_integration_tests`.
4. SP-11: `GET /api/nodes/observed-nodes/{uuid}/`; `GET …/by-meshtastic-id/{int}/` → 302.
