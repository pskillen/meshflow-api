# Phase 2 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 2 / rename execution** — not the [#266](https://github.com/pskillen/meshflow-api/issues/266) epic breakdown.

---

## Phase 2 / 2.1 — ingest & position

- [ ] **Close [#298](https://github.com/pskillen/meshflow-api/issues/298)** only after production deploy of api #331 + bot #103 and SQL shows `rx_log_data` + non-zero MC NLS lat/lon (checklist on issue).
- [ ] **Ingest non-ADVERT `rx_log_data`** (`TEXT_MSG`, `PATH`, …) — bot still `MeshCoreSkipUpload` for those shapes.
- [ ] **Remove ADVERT flattening from bot serializer** — Phase 1 compat shape kept intentionally.
- [ ] **`MeshCoreAdvertPacket` MTI subclass** — not landed; bare `MeshCoreRawPacket` + `event_type` still canonical store.
- [ ] **`original_mt_packet` on `Position`**; `protocol` column on `Position`; altitude/heading from ADVERT; `adv_flags` / `adv_type` → role; public `latest_meshcore_location_source` in OpenAPI — deferred at Phase 2 API close.

---

## Rename track (SP-06–SP-11) — merge & deploy

- [ ] Merge [#324](https://github.com/pskillen/meshflow-api/pull/324), [ui#271](https://github.com/pskillen/meshflow-ui/pull/271), [bot#98](https://github.com/pskillen/meshflow-bot/pull/98); close [#313](https://github.com/pskillen/meshflow-api/issues/313)–[#318](https://github.com/pskillen/meshflow-api/issues/318) when verified on `main`.
- [ ] **Deploy order:** api #324 → ui #271 (bot #98 anytime). Migrations through `nodes.0041`, `constellations/0008`, `text_messages/0007`, `packets/0018`.
- [ ] **`tests/integration/`** full run after deploy (`pytest tests/integration/ -v`).
- [ ] **Release notes** — numeric observed-node bookmarks → UI redirect + api `by-meshtastic-id`.
- [ ] **Feeder upsert gap** — bot may send `location_source` / `channel_utilization`; api maps metrics from `meshtastic_*` only; optional `NodeSerializer` aliases.
- [ ] **OpenAPI path param naming** — ingest/stats still use parameter name `node_id` (Meshtastic nodenum); cosmetic rename to `meshtastic_node_id` deferred.
- [ ] **Cursor rename index** — mark SP-05 `skipped` in `meshcore-rename-index.plan.md` when convenient (plan repo).

### SP-08 / stats paths (by design, document only)

- [ ] `/stats/nodes/{node_id}/*` and bulk metrics `node_ids` remain Meshtastic nodenums.
- [ ] Optional OpenAPI pass to label those params “Meshtastic node id” consistently.

### SP-09 / UI branding (deferred from SP-09 delivery)

- [ ] Remove `meshtastic-api.ts` shim after callers migrated.
- [ ] Rename `src/lib/meshtastic.ts` to neutral module name.
- [ ] Production `config.json`: add `apis.meshflow` (ui falls back to `apis.meshtastic` today).

### SP-10 / bot wire (deferred)

- [ ] `MeshNodeSerializer` still POSTs `hw_model` / `public_key`; api accepts aliases — optional send `meshtastic_*` and drop aliases after bot deploy.

### SP-11 / links

- [ ] **Heatmap / traceroute map** — links may use `/nodes/{meshtastic_node_id}` without `internal_id`; redirect works; optional enrich API payloads later.

### Carried from SP-01–SP-04 (labelling / docs)

- [ ] `meshtastic_hw_model` help_text (SP-02 gap); optional `meshtastic_is_licensed` / `meshtastic_is_unmessagable` help_text migrations.
- [ ] OpenAPI `ObservedNodeSearch` may omit `internal_id` in schema while serializer returns it.
- [ ] `/nodes/environment-metrics-bulk/` Meshtastic-only description (same gap as device-metrics-bulk).
- [ ] `meshcore_packets/0002` index rename — manual fix if `0001_initial` index names diverged on a DB.
- [ ] Stored traceroute hop JSON key `node_id` in DB (SP-05 skipped; API enrichment uses `meshtastic_node_id`).
- [ ] Test factories — legacy kwargs (`node_id`, `hw_model`, …) remain aliases in `create_observed_node`.
- [ ] **UI nav parity** — [ui#269](https://github.com/pskillen/meshflow-ui/issues/269) (Meshtastic/MeshCore sidebar sections), separate from rename.

---

## Bot version ([#99](https://github.com/pskillen/meshflow-bot/issues/99))

- [ ] Merge/deploy [#325](https://github.com/pskillen/meshflow-api/pull/325) before bot [#100](https://github.com/pskillen/meshflow-bot/pull/100) fleet upgrade.
- [ ] Coordinate migration numbering: `nodes/0042` (bot version) vs `0043+` (`node_id_str` drop) on branches that contain both.

---

## Phase 2.2 — text messages & channels ([#296](https://github.com/pskillen/meshflow-api/issues/296), [#297](https://github.com/pskillen/meshflow-api/issues/297))

Design: [text-message-channels.md](./text-message-channels.md) (device = source of truth for channel config; API mirror via sync).

**API** (branch `api-296/paddy/mc-text-channels` — merge pending)

- [x] `MessageChannel`: `mc_channel_type`, `mc_hashtag`; uniqueness `(constellation, protocol, mc_channel_idx)`.
- [x] `ManagedNode.mc_channels` M2M; optional `mc_channels_synced_at`.
- [x] `POST …/mc-channel-sync/` — reconcile mirror from bot device snapshot.
- [x] `resolve_mc_channel` — prefer feeder M2M; placeholder before first sync.
- [x] `TextMessage`: `protocol`, `original_mc_packet`, nullable `sender`, provenance CHECK.
- [x] `MeshCoreTextMessageService` + `meshcore_text_packet_received` receiver.
- [x] History API: `protocol` filter; MC channel broadcast; MC `heard` observations.
- [x] WS `apply_mc_channel_config` (UI → device; bot re-syncs after).
- [x] OpenAPI + tests.

**Bot (child #297)** (branch `api-296/paddy/mc-text-channels` — merge pending)

- [x] Read device channel table on connect; `POST mc-channel-sync`.
- [x] WS handler: apply config → write device → re-sync.
- [x] Enable MC WebSocket when storage API configured.
- [x] meshcore_py channel read/write spike.

**UI (child #297)** (branch `api-296/paddy/mc-channel-settings` — merge pending)

- [x] Display synced `mc_channels`; apply-to-radio (not API-only save).
- [ ] Sync status / bot offline messaging (basic toasts only; richer UX deferred).

**Deferred (2.2)**

- [ ] Three-way merge / conflict UI when device and staged edits diverge.
- [ ] Periodic background sync without reconnect.
- [ ] MC DM history API / message history UI.

---

## Cross-phase tickets (not rename SP work)

- [ ] **API v1 ingest retirement** — [#319](https://github.com/pskillen/meshflow-api/issues/319), bot [#95](https://github.com/pskillen/meshflow-bot/issues/95).
- [ ] **`TextMessage` dual FK** — Phase 2.2 ([#296](https://github.com/pskillen/meshflow-api/issues/296)); see checklist above.
- [ ] **Formatting toolchain alignment** (Black / flake8 / isort / Ruff) — bot [#101](https://github.com/pskillen/meshflow-bot/issues/101).
- [ ] **Rename Django app `packets` or `/api/packets/` URL prefix** — out of scope for #307.

---

## Resolved (do not re-open)

- [x] SP-01–SP-04 merged ([#320](https://github.com/pskillen/meshflow-api/pull/320)–[#323](https://github.com/pskillen/meshflow-api/pull/323), ui [#268](https://github.com/pskillen/meshflow-ui/pull/268), [#270](https://github.com/pskillen/meshflow-ui/pull/270)).
- [x] SP-05 closed skipped ([#311](https://github.com/pskillen/meshflow-api/issues/311)).
- [x] Observed-node detail by `internal_id` — in open #324 / ui#271 (implementation done on branch).
- [x] UI traceroute-links URL uses `internal_id` — fixed on ui#271.
- [x] Drop stored `ObservedNode.node_id_str` — [#294](https://github.com/pskillen/meshflow-api/issues/294) / PR #326.
- [x] Phase 2.1 api + bot PRs ([#331](https://github.com/pskillen/meshflow-api/pull/331), [bot#103](https://github.com/pskillen/meshflow-bot/pull/103)).
