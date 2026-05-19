# MeshCore / multi-protocol — refactoring progress (rename & labelling)

Living tracker for the [rename audit index](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md) sub-plans.

**Sub-plans:** `IdeaProjects/MeshFlow/.cursor/plans/` · **Sub-epic:** [#307](https://github.com/pskillen/meshflow-api/issues/307) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266))

**Update this file in every PR** that executes a sub-plan (even doc-only PRs).

**Convention**

- Status: `not_started` | `in_progress` | `merged` | `deferred` | `skipped`
- Link the GitHub issue when filed; link the PR when opened.
- After merge, set status to `merged` and note the merge commit or PR number.

**Last updated:** 2026-05-19 — SP-06–SP-11 implemented; PRs open (awaiting merge).

---

## Sub-plan index

| ID | Sub-plan | Repos | PRs | Status | Issue | PR |
|----|----------|-------|-----|--------|-------|-----|
| SP-01 | OpenAPI contract docs | api | 1 | merged | [#308](https://github.com/pskillen/meshflow-api/issues/308) | [#320](https://github.com/pskillen/meshflow-api/pull/320) |
| SP-02 | Comment-only labelling | api, bot, ui | 1–3 | merged | [#309](https://github.com/pskillen/meshflow-api/issues/309) | [#321](https://github.com/pskillen/meshflow-api/pull/321) · [bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [ui#267](https://github.com/pskillen/meshflow-ui/pull/267) |
| SP-03 | `node_id` → `meshtastic_node_id` | api, bot, ui | 1 (coordinated) | merged | [#310](https://github.com/pskillen/meshflow-api/issues/310) | [#322](https://github.com/pskillen/meshflow-api/pull/322) · [ui#268](https://github.com/pskillen/meshflow-ui/pull/268) |
| SP-04 | ObservedNode MT identity fields | api, ui | 1 | merged | [#312](https://github.com/pskillen/meshflow-api/issues/312) | [#323](https://github.com/pskillen/meshflow-api/pull/323) · [ui#270](https://github.com/pskillen/meshflow-ui/pull/270) |
| SP-05 | MtRawPacket wire + observations | api | — | skipped | [#311](https://github.com/pskillen/meshflow-api/issues/311) | — |
| SP-06 | ManagedNode channels + constellation bot defaults | api, ui | 1 | in_progress | [#313](https://github.com/pskillen/meshflow-api/issues/313) | [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-07 | TextMessage MT fields | api, ui | 1 | in_progress | [#314](https://github.com/pskillen/meshflow-api/issues/314) | [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-08 | NodeLatestStatus / metrics MT columns | api, ui | 1 | in_progress | [#315](https://github.com/pskillen/meshflow-api/issues/315) | [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-09 | UI client branding | ui | 1 | in_progress | [#316](https://github.com/pskillen/meshflow-api/issues/316) | [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |
| SP-10 | Bot local naming | bot | 1 | in_progress | [#317](https://github.com/pskillen/meshflow-api/issues/317) | [bot#98](https://github.com/pskillen/meshflow-bot/pull/98) |
| SP-11 | ObservedNode lookup by `internal_id` | api, ui | 1 | in_progress | [#318](https://github.com/pskillen/meshflow-api/issues/318) | [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) |

**Batch PRs (SP-06–SP-11):** api + ui share branch `api-307/pskillen/meshcore-rename-sp06-sp11` (five conventional commits on ui). Bot SP-10 is separate: `api-317/pskillen/meshcore-rename-sp10-bot-local`.

Parent index: [meshcore-rename-index](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md) · Phase context: [implementation-plan.md](./implementation-plan.md)

---

## Per-step notes (append as work lands)

### SP-01 — OpenAPI contract docs

- **Merged:** 2026-05-19 ([#320](https://github.com/pskillen/meshflow-api/pull/320))
- **Branch:** `api-308/pskillen/meshcore-rename-sp01-openapi`
- **Delivered in #320:**
  - `POST /packets/{node_id}/ingest/` and `/packets/{node_id}/nodes/` (was unscoped paths)
  - `ObservedNode.internal_id` → `string` / `uuid` in schema
  - Meshtastic-only descriptions: `device-metrics-bulk`, nested `device_metrics` / `environment_metrics` / `power_metrics`, `/stats/nodes/{node_id}/*`
  - Legacy **Packets** tag definition → points at **Meshtastic packets**
  - Deprecated `POST /raw-packet/` (v1 bot URL; not in current Django urlconf)
  - Observed-node detail `GET|PUT|DELETE /nodes/observed-nodes/{node_id}/` — MT nodenum; MeshCore via list + `protocol` until #318
- **Notes:** Doc-only; no migrations. Closes #308.

### SP-02 — Comment-only labelling

- **Merged:** 2026-05-19 — api `0bcc063` ([#321](https://github.com/pskillen/meshflow-api/pull/321)), bot `13eced8` ([#96](https://github.com/pskillen/meshflow-bot/pull/96)), ui `db82769` ([#267](https://github.com/pskillen/meshflow-ui/pull/267))
- **Branch:** `api-309/pskillen/meshcore-rename-sp02-comments` (api, bot, ui)
- **Delivered (no JSON renames):**
  - **api:** `ObservedNode` help_text (`mac_addr`, names, `public_key`, `role`); `NodeLatestStatus.inferred_max_hops`; `RoleSource` / `LocationSource` module docstrings; `BaseNodeItem` (unchanged, already labelled); `TextMessage.original_packet` help_text; serializer/view docstrings; OpenAPI `ObservedNode`, nested `latest_*` (position/device/env/power), `TextMessage`, list `GET /nodes/observed-nodes/`
  - **api migrations (follow-up on #321):** `nodes/0037` help_text-only `AlterField`s; `text_messages/0006` `original_packet` help_text; `meshcore_packets/0002` `RenameIndex` (manual names from `0001_initial` → Django `Meta.indexes` auto names)
  - **bot:** `src/radio/events.py` (`portnum`, `from_id`/`to_id` with `mc:` examples, hops); `interface.py` (`local_nodenum`, `send_traceroute` MT-only); `StorageAPI.py` v2 Meshtastic ingest vs `/api/meshcore/packets/ingest/`
  - **ui:** `src/lib/models.ts` JSDoc on `ObservedNode` + MT-only nested metrics; API client comments for mixed resource + `protocol` filter
- **PRs:** [#321](https://github.com/pskillen/meshflow-api/pull/321) · [meshflow-bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [meshflow-ui#267](https://github.com/pskillen/meshflow-ui/pull/267)
- **Notes:** #309 closed via api #321. Detail route was Meshtastic numeric id until SP-11 ([#318](https://github.com/pskillen/meshflow-api/issues/318)).

### SP-03 — `meshtastic_node_id`

- **Merged:** 2026-05-19 — api ([#322](https://github.com/pskillen/meshflow-api/pull/322)), ui ([#268](https://github.com/pskillen/meshflow-ui/pull/268)); bot: no PR (no code changes)
- **Branch:** `api-310/pskillen/meshcore-rename-sp03-meshtastic-node-id` (api, ui)
- **Delivered:**
  - **api ([#322](https://github.com/pskillen/meshflow-api/pull/322)):** `RenameField` migration `0037_rename_node_id_meshtastic_node_id` (+ `0038` help_text alters); `ObservedNode` / `ManagedNode` field + CHECK constraint; serializers, views (`lookup_field=meshtastic_node_id`, `lookup_url_kwarg=node_id`), admin, packets ingest auth, stats/traceroute/dx/mesh_monitoring/ws; `openapi.yaml` JSON field rename; unit tests; `tests/integration/` JSON assertions updated
  - **bot:** No payload change (node upsert still uses JSON `id`; ingest URL path `<int:node_id>` unchanged)
  - **ui ([#268](https://github.com/pskillen/meshflow-ui/pull/268)):** `ObservedNode` / `ManagedNode` types and all `.meshtastic_node_id` usages; Playwright fixtures
- **PRs:** [#322](https://github.com/pskillen/meshflow-api/pull/322) · [meshflow-ui#268](https://github.com/pskillen/meshflow-ui/pull/268)
- **Notes:** #310 closed. URL path segment and Django kwarg remain `node_id` on many routes; observed-node **detail** lookup moved to `internal_id` in SP-11.

### SP-04 — ObservedNode MT identity fields

- **Merged:** 2026-05-19 ([#323](https://github.com/pskillen/meshflow-api/pull/323) · [ui#270](https://github.com/pskillen/meshflow-ui/pull/270))
- **Branch:** `api-312/pskillen/meshcore-rename-sp04-observed-node-mt` (api, ui)
- **Delivered:**
  - **api ([#323](https://github.com/pskillen/meshflow-api/pull/323)):** `RenameField` migration `0039_rename_observednode_meshtastic_identity_fields`; model, `ObservedNodeSerializer`, admin, infrastructure filter (`meshtastic_role__in`), mesh monitoring eligibility/summary; `NodeInfoPacketService` copies `NodeInfoPacket.*` onto `ObservedNode.meshtastic_*`; `NodeSerializer` (feeder upsert) exposes `meshtastic_*` in responses and accepts legacy `hw_model` / `public_key` on request; `openapi.yaml`; unit + integration test JSON keys
  - **ui ([#270](https://github.com/pskillen/meshflow-ui/pull/270)):** `ObservedNode` type and components; test fixtures
- **Out of scope (unchanged):** `NodeInfoPacket` / `MtRawPacket` columns and NODEINFO ingest wire JSON (SP-05 skipped); bot `MeshNodeSerializer.to_api_dict` still sends `hw_model` / `public_key`; `node_id_str` → `display_id` (comment-only defer); optional later `mac_addr` → `meshtastic_mac_addr`
- **Notes:** MeshCore ingest does not set `meshtastic_*` identity fields. Feeder upsert wire shape still uses `id` / `macaddr` / nested `user`.

### SP-05 — Packet wire fields

- **Merged:** —
- **Skipped:** 2026-05-19 — [#311](https://github.com/pskillen/meshflow-api/issues/311) closed without implementation
- **Rationale:** `MtRawPacket`, `NodeInfoPacket`, and related ingest serializers already live on Meshtastic-only models/tables; column names describe Meshtastic wire semantics. SP-04 copies `NodeInfoPacket` → `ObservedNode.meshtastic_*` at the domain boundary. Stored traceroute hop JSON and NODEINFO camelCase ingest payloads stay unchanged.
- **Plan:** [meshcore-rename-sp05-packet-wire.plan.md](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-sp05-packet-wire.plan.md) (not executed)

### SP-06 — Channels + constellation

- **Merged:** — (awaiting [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271))
- **Branch:** `api-307/pskillen/meshcore-rename-sp06-sp11` (api, ui)
- **Delivered:**
  - **api ([#324](https://github.com/pskillen/meshflow-api/pull/324)):** `ManagedNode.meshtastic_channel_0..7`; `Constellation.bot_default_ignore_meshtastic_portnums` / `bot_default_meshtastic_hop_limit`; migrations `nodes/0040`, `constellations/0008`; serializers, admin, `openapi.yaml`, unit tests
  - **ui ([#271](https://github.com/pskillen/meshflow-ui/pull/271)):** `OwnedManagedNode` channel mappings; `NodeSettings` / `SetupManagedNode` / `MonitoredNodesChannelUtilChart`; `patchManagedNode` body keys
- **Notes:** Managed-node URLs still use `meshtastic_node_id` (unchanged). Deploy api before ui.

### SP-07 — Text messages

- **Merged:** — (awaiting [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271))
- **Delivered:**
  - **api:** `recipient_meshtastic_node_id`, `reply_to_meshtastic_packet_id`; migration `text_messages/0007`; ingest service, serializers, `openapi.yaml`
  - **ui:** `TextMessage` types, `MessageList`, `useMessagesWithWebSocket` filter param `sender_node_id` unchanged (still Meshtastic nodenum for API query)

### SP-08 — Metrics columns

- **Merged:** — (awaiting [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271))
- **Delivered:**
  - **api:** `meshtastic_location_source`, `meshtastic_precision_bits`, `meshtastic_channel_utilization`, `meshtastic_air_util_tx`, `meshtastic_inferred_max_hops` on `NodeLatestStatus`, `Position`, `DeviceMetrics`, and packet payload tables; migrations `nodes/0041`, `packets/0018`; serializers + `openapi.yaml`
  - **ui:** Nested `latest_*` / metrics chart types; device/environment/power **history** endpoints called with `internal_id` (UUID); packet stats charts still use `meshtastic_node_id` for `/stats/nodes/{id}/*`
- **Notes:** ORM annotation aliases `latest_*` / `last_*` unchanged internally. Bulk metrics endpoints still take comma-separated Meshtastic nodenums (`node_ids`).

### SP-09 — UI branding

- **Merged:** — (awaiting [ui#271](https://github.com/pskillen/meshflow-ui/pull/271))
- **Delivered (ui only):**
  - `src/lib/api/meshflow-api.ts` — `MeshflowApi` class; `getObservedNode` / `getObservedNodes`; deprecated aliases on `meshtastic-api.ts` shim
  - `useMeshflowApi()` + `config.apis.meshflow` (falls back to `config.apis.meshtastic`)
  - Hooks migrated to `useMeshflowApi` where touched in SP-06–SP-11 batch
- **Not done (deferred):** Rename file `meshtastic.ts` → neutral helper module; remove shim entirely; rename `meshtastic-api.ts` file; update remote `config.json` examples in deploy docs only

### SP-10 — Bot local naming

- **Merged:** — (awaiting [bot#98](https://github.com/pskillen/meshflow-bot/pull/98))
- **Branch:** `api-317/pskillen/meshcore-rename-sp10-bot-local` (bot only)
- **Delivered:**
  - `local_nodenum_provider` → `local_meshtastic_nodenum_provider` on `StorageAPIWrapper`
  - `get_by_id` → `get_by_radio_id` on node DB implementations
  - Optional `canonical_id` ctor alias on `MeshNode.User`
- **Not done:** Rename `MeshNodeSerializer` wire keys (`hw_model` / `public_key` → `meshtastic_*`); bot still POSTs legacy keys accepted by api `NodeSerializer` aliases

### SP-11 — Lookup `internal_id`

- **Merged:** — (awaiting [#324](https://github.com/pskillen/meshflow-api/pull/324) · [ui#271](https://github.com/pskillen/meshflow-ui/pull/271))
- **Delivered:**
  - **api:** `ObservedNodeViewSet.lookup_field = internal_id`; claim, RF profile/propagation, environment-settings, nested metrics, `traceroute-links` use `<uuid:internal_id>`; `GET …/by-meshtastic-id/{meshtastic_node_id}/` → 302 to canonical detail URL; `openapi.yaml` path `{internal_id}`; tests use `reverse(..., kwargs={"internal_id": ...})`
  - **ui:** `NodeDetails` + `LegacyMeshtasticNodeRedirect` for numeric `/nodes/:id`; links on `ObservedNode` use `internal_id`; `useNodeSuspense(internalId)`; claim/release/cancel use UUID; `ObservedNode.internal_id` typed `string` + `TEST_OBSERVED_INTERNAL_ID` in tests
- **Breaking:** Clients must use UUID for observed-node detail and nested routes after api deploy. Managed nodes, packet ingest, and stats paths still use Meshtastic numeric id.
- **ui follow-up (done on #271):** `getNodeTracerouteLinks` / `useNodeTracerouteLinks` use `internal_id` for the detail URL.

---

## Outstanding and observations

_Capture follow-ups so they are not lost between sub-plans. Remove or strike through items when resolved._

### SP-06–SP-11 batch — merge & deploy

- [ ] Merge [#324](https://github.com/pskillen/meshflow-api/pull/324), [ui#271](https://github.com/pskillen/meshflow-ui/pull/271), [bot#98](https://github.com/pskillen/meshflow-bot/pull/98); set SP-06–SP-08, SP-10, SP-11 to `merged` (SP-09 ui-only → `merged` with ui#271).
- [ ] Close tracking issues [#313](https://github.com/pskillen/meshflow-api/issues/313)–[#318](https://github.com/pskillen/meshflow-api/issues/318) when respective scopes are verified on `main`.
- [ ] **Deploy order:** api #324 → ui #271 (bot #98 independent). Run migrations `0040`, `0041`, `constellations/0008`, `text_messages/0007`, `packets/0018`.
- [ ] **`tests/integration/`** — re-run full suite against deployed API with all migrations through `0041` (`pytest tests/integration/ -v`).

### SP-11 / #318 — follow-ups after merge

- [x] **UI traceroute-links URL** — fixed on [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) (`internal_id` in `getNodeTracerouteLinks` / `TracerouteLinksSection`).
- [ ] **Bookmark / external links** — old numeric observed-node URLs work via ui redirect; api `by-meshtastic-id` supports server-side resolution. Document in release notes.
- [ ] **Mesh monitoring** — `createNodeWatch` already uses `observed_node_id` (UUID string); no change needed.
- [ ] **Heatmap / traceroute map links** — ui still links to `/nodes/{meshtastic_node_id}` for types without `internal_id` (`TracerouteRouteNode`, `HeatmapNode`); redirect handles it; optional enrichment: add `internal_id` to those API payloads later.

### SP-08 / #315 — still Meshtastic-numeric paths

- [ ] **`/stats/nodes/{node_id}/*`** — path param remains Meshtastic nodenum (by design); ui `PacketTypeChart` / neighbour stats unchanged.
- [ ] **`/nodes/device-metrics-bulk/`** and **`environment-metrics-bulk/`** — request `node_ids` still comma-separated Meshtastic ids.
- [ ] **OpenAPI** — nested observed-node routes renamed to `{internal_id}` in #324; stats and packet ingest paths still `{node_id}` — optional doc pass to label “Meshtastic node id” consistently.

### SP-09 / #316 — branding cleanup (deferred)

- [ ] Remove `meshtastic-api.ts` shim after callers gone; keep one release cycle with deprecated `useMeshtasticApi` if needed.
- [ ] Rename `src/lib/meshtastic.ts` (role labels / constants) to a protocol-neutral name when convenient.
- [ ] Production `config.json`: add `apis.meshflow` alongside legacy `apis.meshtastic` (ui falls back today).

### SP-10 / #317 — bot wire shape (deferred)

- [ ] **`MeshNodeSerializer`** — still POSTs `hw_model` / `public_key`; api accepts via `NodeSerializer.to_internal_value` aliases. Optional follow-up: send `meshtastic_*` keys and drop aliases on api after bot deploy.

### SP-05 / #311 (skipped)

- [x] Close [#311](https://github.com/pskillen/meshflow-api/issues/311) — no `RenameField` on packet wire tables.
- [ ] **Rename index plan** — optional: mark SP-05 `skipped` in `IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md` (Cursor plans repo).

### Carried from SP-01–SP-04 (still open)

- [ ] **`meshtastic_hw_model` help_text** — field has no `help_text` (SP-02 gap); optional `AlterField` migration.
- [ ] **`meshtastic_is_licensed` / `meshtastic_is_unmessagable` help_text** — optional labelling migration.
- [ ] **OpenAPI `ObservedNodeSearch`** — response schema may still omit `internal_id` (serializer returns it).
- [ ] **`/nodes/environment-metrics-bulk/`** — optional Meshtastic-only description (same gap as SP-01 for `device-metrics-bulk`).
- [ ] **Metric serializer docstrings** — `EnvironmentMetricsSerializer` / `PowerMetricsSerializer` MT protocol notes optional.
- [ ] **`meshcore_packets/0002`** — index renames only where `0001_initial` index names match; manual fix on diverged DBs.
- [ ] **URL path param naming** — OpenAPI still uses parameter name `node_id` on ingest, stats, managed-node routes; only observed-node **detail** uses `{internal_id}` after #324. Optional later epic: rename path param to `meshtastic_node_id` for clarity.
- [ ] **Stored traceroute wire JSON** — `AutoTraceRoute.route` hop arrays still use key `node_id`; enriched API uses `meshtastic_node_id` (intentional; SP-05 skipped).
- [ ] **`Position.node_id` FK column** — Django FK column name unchanged (points at `ObservedNode.internal_id`).
- [ ] **Test factories** — `create_observed_node` legacy kwargs (`node_id`, `role`, `hw_model`, …) remain aliases; prefer `meshtastic_*` in new tests.
- [ ] **meshflow-ui nav parity** — [ui#269](https://github.com/pskillen/meshflow-ui/issues/269) (Meshtastic/MeshCore sidebar sections) — separate from rename sub-plans.

### Deferred to other tickets

- [ ] **API v1 ingest retirement** — [#319](https://github.com/pskillen/meshflow-api/issues/319); bot [#95](https://github.com/pskillen/meshflow-bot/issues/95). Deprecated `POST /raw-packet/` in OpenAPI until bot defaults to v2 only.
- [ ] **`TextMessage` dual FK** (`original_mt_packet` / `original_mc_packet`) — Phase 2 / separate epic.
- [ ] **Drop `ObservedNode.node_id_str` DB column** — separate ADR/amendment.
- [ ] **Rename Django app `packets` or `/api/packets/` URL prefix** — out of scope for rename index.

### Resolved since earlier revisions (do not re-open)

- [x] SP-03 / SP-04 PRs merged ([#322](https://github.com/pskillen/meshflow-api/pull/322), [#323](https://github.com/pskillen/meshflow-api/pull/323), [ui#268](https://github.com/pskillen/meshflow-ui/pull/268), [ui#270](https://github.com/pskillen/meshflow-ui/pull/270)).
- [x] **`ObservedNode.internal_id` in meshflow-ui** — `string` / UUID in [ui#271](https://github.com/pskillen/meshflow-ui/pull/271) (was `number` since SP-02).
- [x] **ObservedNode detail by `internal_id`** — implemented SP-11 ([#318](https://github.com/pskillen/meshflow-api/issues/318)) in [#324](https://github.com/pskillen/meshflow-api/pull/324) / [ui#271](https://github.com/pskillen/meshflow-ui/pull/271).

### Conventions / process

- No operation in `openapi.yaml` uses `tags: [Packets]`; only the global tag definition was clarified.
- OpenAPI operation descriptions link to GitHub issues (e.g. #318); may not render in all Swagger UIs.
- Progress doc updates belong in the **api** PR when closing rename work; this revision is for the open SP-06–SP-11 batch — commit on api branch when #324 is updated or in a small doc-only commit before merge.
