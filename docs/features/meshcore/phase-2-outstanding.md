# Phase 2 — outstanding

Items **skipped**, **incomplete**, or **discovered during Phase 2 / rename execution** — not the [#266](https://github.com/pskillen/meshflow-api/issues/266) epic breakdown.

---

## Phase 2 / 2.1 — ingest & position

- [ ] **Close [#298](https://github.com/pskillen/meshflow-api/issues/298)** only after production deploy of api #331 + bot #103 and SQL shows `rx_log_data` + non-zero MC NLS lat/lon (checklist on issue).
- [ ] **Ingest non-ADVERT `rx_log_data`** (`TEXT_MSG`, `PATH`, …) — bot still `MeshCoreSkipUpload` for those shapes.
- [ ] **Remove ADVERT flattening from bot serializer** — Phase 1 compat shape kept intentionally.
- [ ] **`MeshCoreAdvertPacket` MTI subclass** — not landed; bare `MeshCoreRawPacket` + `event_type` still canonical store.
- [ ] **`original_mt_packet` on `Position`**; `protocol` column on `Position`; altitude/heading from ADVERT; `adv_flags` semantics; public `latest_meshcore_location_source` in OpenAPI — deferred at Phase 2 API close.
- [x] **`adv_type` on ObservedNode** — `meshcore_adv_type` (ui#269 / migration `nodes.0048`); `adv_flags` not yet mapped.

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
- [x] **UI nav parity** — [ui#269](https://github.com/pskillen/meshflow-ui/issues/269) (in PR; see [phase-2-progress.md](./phase-2-progress.md) § UI nav & map parity).
- [x] **MeshCore managed-nodes live status** — `include=status` MC annotations + UI table (api branch; see progress § MeshCore managed-node live status). **Still ship**; does not close [#329](https://github.com/pskillen/meshflow-api/issues/329).
- [ ] **Hourly MC stats snapshots** — [#329](https://github.com/pskillen/meshflow-api/issues/329): `collect_stats_snapshots` / `StatsSnapshot` / dashboard charts; document Meshtastic path first (`docs/features/stats/meshtastic_packets.md`).
- [ ] **UI out of scope for #269** — `/meshtastic/*` URL migration; MeshCore messages / traceroutes / weather screens; server-side `protocol` filter on `GET /nodes/managed-nodes/`.
- [ ] **Node search** still Meshtastic-centric (global sidebar search).

---

## Bot version ([#99](https://github.com/pskillen/meshflow-bot/issues/99))

- [ ] Merge/deploy [#325](https://github.com/pskillen/meshflow-api/pull/325) before bot [#100](https://github.com/pskillen/meshflow-bot/pull/100) fleet upgrade.
- [ ] Coordinate migration numbering: `nodes/0042` (bot version) vs `0043+` (`node_id_str` drop) on branches that contain both.

---

## Phase 2.2 — text messages & channels ([#296](https://github.com/pskillen/meshflow-api/issues/296), [#297](https://github.com/pskillen/meshflow-api/issues/297))

Design: [text-message-channels.md](./text-message-channels.md). **Core 2.2 merged** (api [#333](https://github.com/pskillen/meshflow-api/pull/333), bot [#105](https://github.com/pskillen/meshflow-bot/pull/105), ui [#273](https://github.com/pskillen/meshflow-ui/pull/273)).

**Still open from 2.2 scope**

- [ ] Sync status / bot offline messaging in UI (basic toasts only; richer UX deferred).
- [ ] Three-way merge / conflict UI when device and staged edits diverge.
- [ ] Periodic background sync without reconnect.
- [ ] MC DM history API / message history UI.

---

## Phase 2.2 — staging & ops (discovered 2026-05-21, not in original tickets)

Follow-up after local UI + pre-prod bot + shared Postgres/Redis. Tracked on [#295](https://github.com/pskillen/meshflow-api/issues/295); fixes on [api #335](https://github.com/pskillen/meshflow-api/pull/335), [bot #108](https://github.com/pskillen/meshflow-bot/pull/108).

### Merge / deploy

- [ ] Merge and deploy **api #335** then **bot #108**; restart API ASGI workers after deploy.
- [ ] Run `python manage.py migrate` for `constellations.0010` (MeshCoreMessageChannel proxy) on environments using new admin.

### Resolved in #335 / #108 (do not re-debug as open bugs)

- [x] False **503 feeder not connected** when Redis group key existed — presence check used non-existent `group_channels()` on `channels_redis`.
- [x] **503 command dispatch** / `can not serialize '__proxy__'` on apply — lazy gettext channel labels in WS payload; fixed serializers + `_ws_json_safe()`.
- [x] WS group mismatch with shared API keys — bot must pass `feeder_pubkey_prefix` on `ws/nodes/` URL.
- [x] Legacy paths removed — use `/api/meshcore/feeders/{prefix}/…` only (not `/api/meshcore/feeder/…` or `/api/packets/0/bot-version/` for MC).

### Outstanding (noticed, not fully solved)

- [ ] **Empty device channel table** — bot can connect and sync while `get_channel` scan finds 0 named channels; other tools may show channels on the same radio. Needs device/firmware/meshcore_py investigation; bot logs per-slot scan ([#107](https://github.com/pskillen/meshflow-bot/pull/107)).
- [ ] **Auto-set `mc_pubkey` on first connect** — still manual in admin ([#279](https://github.com/pskillen/meshflow-api/issues/279)).
- [ ] **OpenAPI** — confirm all MC feeder paths and apply responses match deployed code after #335 merge (code was ahead of spec in places during staging).
- [ ] **Admin push action** — dispatches mirror only; editing constellation rows in **MeshCore channels** does not auto-link to `ManagedNode.mc_channels` or push (operators must sync mirror via bot connect or understand M2M).
- [ ] **Dual API (`STORAGE_API_2_*`)** — bot POSTs `mc-channel-sync` (and packets) to **both** APIs when upload enabled; **WebSocket / apply** only on primary `STORAGE_API_ROOT`. Documented in [text-message-channels.md](./text-message-channels.md); UI apply against API 2 while bot WS on API 1 will always 503.

### Intentional / by design (document only)

- Browser JWT WebSocket (`/ws/messages/`) is unrelated to feeder `node_command` groups.
- Apply is **202 dispatched** — device mirror updates after bot re-sync, not synchronously in the HTTP response.
- Split-host dev (local API + pre-prod bot) requires shared **Redis DB 0** (`channels_redis`) and matching `ManagedNode` `internal_id` / `mc_pubkey`; see text-message-channels § “Local API + pre-prod bot”.

---

## Cross-phase tickets (not rename SP work)

- [ ] **Hourly packet stats snapshots (MeshCore)** — [#329](https://github.com/pskillen/meshflow-api/issues/329). Live managed-node counts (2026-05-21) are separate; see [phase-2-progress.md](./phase-2-progress.md) § MeshCore managed-node live status.
- [ ] **API v1 ingest retirement** — [#319](https://github.com/pskillen/meshflow-api/issues/319), bot [#95](https://github.com/pskillen/meshflow-bot/issues/95).
- [ ] **`TextMessage` dual FK** — Phase 2.2 ([#296](https://github.com/pskillen/meshflow-api/issues/296)); see checklist above.
- [ ] **Formatting toolchain alignment** (Black / flake8 / isort / Ruff) — bot [#101](https://github.com/pskillen/meshflow-bot/issues/101).
- [ ] **Rename Django app `packets` or `/api/packets/` URL prefix** — out of scope for #307.

---

## Resolved (do not re-open)

- [x] Phase 2.2 core api/bot/ui ([#333](https://github.com/pskillen/meshflow-api/pull/333), [bot#105](https://github.com/pskillen/meshflow-bot/pull/105), [ui#273](https://github.com/pskillen/meshflow-ui/pull/273)).
- [x] Feeder disambiguation api/bot ([#334](https://github.com/pskillen/meshflow-api/pull/334), [bot#106](https://github.com/pskillen/meshflow-bot/pull/106)) — `mc_pubkey`, feeder-scoped URLs.
- [x] SP-01–SP-04 merged ([#320](https://github.com/pskillen/meshflow-api/pull/320)–[#323](https://github.com/pskillen/meshflow-api/pull/323), ui [#268](https://github.com/pskillen/meshflow-ui/pull/268), [#270](https://github.com/pskillen/meshflow-ui/pull/270)).
- [x] SP-05 closed skipped ([#311](https://github.com/pskillen/meshflow-api/issues/311)).
- [x] Observed-node detail by `internal_id` — in open #324 / ui#271 (implementation done on branch).
- [x] UI traceroute-links URL uses `internal_id` — fixed on ui#271.
- [x] Drop stored `ObservedNode.node_id_str` — [#294](https://github.com/pskillen/meshflow-api/issues/294) / PR #326.
- [x] Phase 2.1 api + bot PRs ([#331](https://github.com/pskillen/meshflow-api/pull/331), [bot#103](https://github.com/pskillen/meshflow-bot/pull/103)).
