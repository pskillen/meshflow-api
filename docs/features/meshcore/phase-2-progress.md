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

**Status:** Merged to `main` (2026-05-21). **Guide:** [text-message-channels.md](./text-message-channels.md). **Issues:** [#296](https://github.com/pskillen/meshflow-api/issues/296), [#297](https://github.com/pskillen/meshflow-api/issues/297).

**meshflow-api — delivered**

- `MessageChannel.mc_channel_type` / `mc_hashtag`; `ManagedNode.mc_channels` M2M + `mc_channels_synced_at`.
- `POST /api/meshcore/feeders/{prefix}/mc-channel-sync/`; `POST …/apply-mc-channel-config/` (WS dispatch).
- `MeshCoreTextMessageService` + `text_messages` receiver; `TextMessage.protocol` + `original_mc_packet`.
- History API `protocol` query; MC `heard` from `MeshCorePacketObservation`.
- `managed_node_ws_group` for MC feeder WebSocket (`node_mc_{internal_id}`).
- Tests: `test_channel_sync.py`, `test_text_message_service.py`.

**meshflow-bot — delivered**

- `read_device_channels` / `apply_device_channels` via meshcore_py; `post_mc_channel_sync` on connect.
- WS `apply_mc_channel_config`; MC feeders enable WebSocket when storage API configured.

**meshflow-ui — delivered**

- MeshCore channel panel on Node Settings (mirror + apply-to-radio).

**Merged to `main` (2026-05-21):** api [#333](https://github.com/pskillen/meshflow-api/pull/333), bot [#105](https://github.com/pskillen/meshflow-bot/pull/105), ui [#273](https://github.com/pskillen/meshflow-ui/pull/273).

---

## MeshCore messages UI ([ui#275](https://github.com/pskillen/meshflow-ui/issues/275))

**Status:** In progress (branch `ui-275/paddy/meshcore-messages` on meshflow-ui).

**meshflow-ui — delivered (pending PR)**

- `/meshcore/messages` — channel-scoped history via shared `ProtocolMessageHistoryPage`; `GET /api/messages/text/?protocol=meshcore`.
- Flattened MeshCore nav: **Messages**, **Nodes** (map on nodes page), **Managed nodes**; removed standalone `/meshcore/map` (redirect to `/meshcore/nodes`).
- Protocol-scoped unread badges on Meshtastic and MeshCore **Messages** nav links (WebSocket `protocol` on `TextMessage`).
- Meshtastic `/messages` is channels-only (removed broken **By Node** tab).
- `MessageItem` MC heard display (observer `node_id_str` string rows from API).

**meshflow-api:** no code changes; uses Phase 2.2 history API + WS payload `protocol` field.

**Still open:** MC DM / contact message history UI (separate from channel history).

---

## Feeder identity & apply fixes ([#295](https://github.com/pskillen/meshflow-api/issues/295))

**Status:** Core identity merged; staging fixes on branch `api-295/paddy/mc-feeder-identity` — [api #335](https://github.com/pskillen/meshflow-api/pull/335), [bot #108](https://github.com/pskillen/meshflow-bot/pull/108) (open at last update).

**meshflow-api — delivered**

- `ManagedNode.mc_pubkey` (64 hex, unique per constellation); feeder-scoped routes:
  - `POST /api/meshcore/feeders/{prefix}/packets/ingest/`
  - `POST /api/meshcore/feeders/{prefix}/mc-channel-sync/`
  - `PUT /api/meshcore/feeders/{prefix}/bot-version/`
- `resolve_meshcore_feeder()` + structured 403 codes (`feeder_not_linked`, `feeder_identity_ambiguous`, `feeder_pubkey_mismatch`, `feeder_pubkey_not_configured`).
- **Feeder WebSocket:** `NodeConsumer` joins `node_mc_{internal_id}` using `feeder_pubkey_prefix` query param when multiple feeders share an API key.
- **Apply path fixes (staging):**
  - `feeder_ws_group_has_subscribers` probes Redis group ZSET (`asgi:group:…`) — `group_channels()` does not exist on `channels_redis` 4.x.
  - `apply_mc_channel_config` payloads use plain `PUBLIC`/`HASHTAG` strings + `_ws_json_safe()` before `group_send` (gettext `__proxy__` broke msgpack).
  - `meshcore_packets/services/channel_apply.py` shared by REST apply and Django admin push action.
- **Django admin:** `MeshCoreMessageChannel` proxy (MC-only list); ManagedNode **read-only** device mirror table (`#` prefix for hashtags); admin action **Push MC channel config to feeder device**.
- Migration `constellations/0010_meshcore_message_channel_proxy.py`.
- Docs: [feeder-bootstrap.md](./feeder-bootstrap.md), [text-message-channels.md](./text-message-channels.md), [REDIS.md](../../REDIS.md) (MC groups).

**meshflow-bot — delivered** ([#106](https://github.com/pskillen/meshflow-bot/pull/106) merged; [#108](https://github.com/pskillen/meshflow-bot/pull/108) open)

- Feeder-scoped storage URLs + `X-MeshCore-Feeder-Pubkey`; no `PUT /api/packets/0/bot-version/` for MC.
- WS URL appends `feeder_pubkey_prefix` automatically after `SELF_INFO`.
- Channel sync logging + per-slot `get_channel` scan warning when device reports zero named channels ([#107](https://github.com/pskillen/meshflow-bot/pull/107) merged).

**Verified in dev:** local UI → local API `apply-mc-channel-config` → 202 when bot WS on primary API and both share Redis DB 0 with pre-prod bot uploading to both APIs.

---

## UI nav & map parity ([ui#269](https://github.com/pskillen/meshflow-ui/issues/269))

**Status:** In progress (branch `ui-269/paddy/meshtastic-meshcore-nav-parity` on meshflow-ui; API field on `ui-269/paddy/meshcore-adv-type-on-observed-node`).

**meshflow-ui — delivered (pending PR)**

- Sidebar: **Meshtastic** and **MeshCore** sections; Dashboard and Weather remain top-level.
- Meshtastic **Map** in nav (`/map`); MeshCore **Managed nodes** (`/meshcore/managed-nodes`). Standalone MC **Map** nav item superseded by ui#275 (map on `/meshcore/nodes` only).
- Shared `ProtocolMapPage`, `ProtocolNodesPage`, `ProtocolManagedNodesPage` (legacy URLs unchanged).
- MeshCore map legend uses ADV_TYPE roles (Chat / Repeater / Room / Sensor), not Meshtastic role swatches.
- **MeshCore node detail follow-ups** (same UI branch, separate commits): no bogus Meshtastic traceroute history when `meshtastic_node_id` is 0; statistics charts tolerate missing `packet_types`; hide Traceroutes / Monitoring tabs; node-detail map uses MC legend.

**meshflow-api — delivered (pending PR)**

- `ObservedNode.meshcore_adv_type` from ADVERT `adv_type` on ingest; migration `nodes/0048`; OpenAPI field.

---

## MeshCore managed-node live status (API + UI table)

**Status:** Implemented on branch `ui-269/paddy/meshcore-adv-type-on-observed-node` (api commit `fix(api): MeshCore managed node status and packet counts`); ship with or after ui#269 PRs.

**Problem:** `GET /api/nodes/managed-nodes/?include=status` annotated `ObservedNode` and packet counts only via `meshtastic_node_id` and `PacketObservation`. MeshCore feeders (`protocol=2`, `mc_pubkey`, often `meshtastic_node_id=0`) showed zeros for packets/hr, last packet ingested, and radio last heard on the MeshCore managed-nodes page.

**Delivered (meshflow-api)**

- `ManagedNodeViewSet._annotate_common_fields` / `_annotate_status_fields`: join `ObservedNode` by `mc_pubkey` for MC; count `MeshCorePacketObservation` for `packets_last_hour` / `packets_last_24h`.
- `nodes.tasks.update_managed_node_statuses`: refresh `ManagedNodeStatus.last_packet_ingested_at` from `MeshCorePacketObservation` for MC feeders.
- Test: `test_managed_nodes_status_fields_meshcore_feeder`.

**Relationship to [#329](https://github.com/pskillen/meshflow-api/issues/329) (hourly stats snapshots)**

| Area | This work | #329 |
| --- | --- | --- |
| **Consumer** | MeshCore managed-nodes table (`include=status`), same fields as Meshtastic list | Dashboard / `usePacketStats`, `GET /api/stats/snapshots/`, `collect_stats_snapshots` |
| **Mechanism** | Live SQL annotations + 5‑min `ManagedNodeStatus` refresh | Hourly Celery at :05 UTC → `StatsSnapshot` JSON (`packet_volume`, `online_nodes`, …) |
| **Data** | `MeshCorePacketObservation` + `ObservedNode` (MC) | `MeshCoreRawPacket` / MC observed nodes in snapshot collectors (not implemented yet) |

**Overlap:** both touch MC packet volume over time. **Not a substitute:** #329 remains required for historical hourly snapshots and stats API parity; this fix only unblocks the operational managed-feeder table and reuses the same observation rows #329 will eventually aggregate.

**Docs:** [RECENCY.md](../../RECENCY.md) § managed-node annotations (protocol split). Task 1 of #329: [packet-stats/meshtastic.md](../packet-stats/meshtastic.md) (see [packet-stats-progress.md](../packet-stats/packet-stats-progress.md)).

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
