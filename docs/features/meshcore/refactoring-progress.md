# MeshCore / multi-protocol — refactoring progress (rename & labelling)

Living tracker for the [rename audit index](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md) sub-plans.

**Sub-plans:** `IdeaProjects/MeshFlow/.cursor/plans/` · **Sub-epic:** [#307](https://github.com/pskillen/meshflow-api/issues/307) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266))

**Update this file in every PR** that executes a sub-plan (even doc-only PRs).

**Convention**

- Status: `not_started` | `in_progress` | `merged` | `deferred` | `skipped`
- Link the GitHub issue when filed; link the PR when opened.
- After merge, set status to `merged` and note the merge commit or PR number.

---

## Sub-plan index

| ID | Sub-plan | Repos | PRs | Status | Issue | PR |
|----|----------|-------|-----|--------|-------|-----|
| SP-01 | OpenAPI contract docs | api | 1 | merged | [#308](https://github.com/pskillen/meshflow-api/issues/308) | [#320](https://github.com/pskillen/meshflow-api/pull/320) |
| SP-02 | Comment-only labelling | api, bot, ui | 1–3 | merged | [#309](https://github.com/pskillen/meshflow-api/issues/309) | [#321](https://github.com/pskillen/meshflow-api/pull/321) · [bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [ui#267](https://github.com/pskillen/meshflow-ui/pull/267) |
| SP-03 | `node_id` → `meshtastic_node_id` | api, bot, ui | 1 (coordinated) | merged | [#310](https://github.com/pskillen/meshflow-api/issues/310) | [#322](https://github.com/pskillen/meshflow-api/pull/322) · [ui#268](https://github.com/pskillen/meshflow-ui/pull/268) |
| SP-04 | ObservedNode MT identity fields | api, ui | 1 | in_progress | [#312](https://github.com/pskillen/meshflow-api/issues/312) | [#323](https://github.com/pskillen/meshflow-api/pull/323) · [ui#270](https://github.com/pskillen/meshflow-ui/pull/270) |
| SP-05 | MtRawPacket wire + observations | api | — | skipped | [#311](https://github.com/pskillen/meshflow-api/issues/311) | — |
| SP-06 | ManagedNode channels + constellation bot defaults | api, ui | 1 | not_started | [#313](https://github.com/pskillen/meshflow-api/issues/313) | |
| SP-07 | TextMessage MT fields | api, ui | 1 | not_started | [#314](https://github.com/pskillen/meshflow-api/issues/314) | |
| SP-08 | NodeLatestStatus / metrics MT columns | api | 1 | not_started | [#315](https://github.com/pskillen/meshflow-api/issues/315) | |
| SP-09 | UI client branding | ui | 1 | not_started | [#316](https://github.com/pskillen/meshflow-api/issues/316) | |
| SP-10 | Bot local naming | bot | 1 | not_started | [#317](https://github.com/pskillen/meshflow-api/issues/317) | |
| SP-11 | ObservedNode lookup by `internal_id` | api, ui | 1 | deferred | [#318](https://github.com/pskillen/meshflow-api/issues/318) | |

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
- **Notes:** Doc-only; no migrations. Closes #308 when #320 merges.

### SP-02 — Comment-only labelling

- **Merged:** 2026-05-19 — api `0bcc063` ([#321](https://github.com/pskillen/meshflow-api/pull/321)), bot `13eced8` ([#96](https://github.com/pskillen/meshflow-bot/pull/96)), ui `db82769` ([#267](https://github.com/pskillen/meshflow-ui/pull/267))
- **Branch:** `api-309/pskillen/meshcore-rename-sp02-comments` (api, bot, ui)
- **Delivered (no JSON renames):**
  - **api:** `ObservedNode` help_text (`mac_addr`, names, `public_key`, `role`); `NodeLatestStatus.inferred_max_hops`; `RoleSource` / `LocationSource` module docstrings; `BaseNodeItem` (unchanged, already labelled); `TextMessage.original_packet` help_text; serializer/view docstrings; OpenAPI `ObservedNode`, nested `latest_*` (position/device/env/power), `TextMessage`, list `GET /nodes/observed-nodes/`
  - **api migrations (follow-up on #321):** `nodes/0037` help_text-only `AlterField`s; `text_messages/0006` `original_packet` help_text; `meshcore_packets/0002` `RenameIndex` (manual names from `0001_initial` → Django `Meta.indexes` auto names)
  - **bot:** `src/radio/events.py` (`portnum`, `from_id`/`to_id` with `mc:` examples, hops); `interface.py` (`local_nodenum`, `send_traceroute` MT-only); `StorageAPI.py` v2 Meshtastic ingest vs `/api/meshcore/packets/ingest/`
  - **ui:** `src/lib/models.ts` JSDoc on `ObservedNode` + MT-only nested metrics; `meshtastic-api.ts` list/detail comments for mixed resource + `protocol` filter
- **PRs:** [#321](https://github.com/pskillen/meshflow-api/pull/321) · [meshflow-bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [meshflow-ui#267](https://github.com/pskillen/meshflow-ui/pull/267)
- **Notes:** #309 closed via api #321. Detail route remains Meshtastic numeric id until [#318](https://github.com/pskillen/meshflow-api/issues/318). **Migration numbering:** SP-02 took `nodes/0037` for help_text before SP-03 `RenameField`; confirm deploy order on `main` if both landed close together.

### SP-03 — `meshtastic_node_id`

- **Merged:** 2026-05-19 — api ([#322](https://github.com/pskillen/meshflow-api/pull/322)), ui ([#268](https://github.com/pskillen/meshflow-ui/pull/268)); bot: no PR (no code changes)
- **Branch:** `api-310/pskillen/meshcore-rename-sp03-meshtastic-node-id` (api, ui)
- **Delivered:**
  - **api ([#322](https://github.com/pskillen/meshflow-api/pull/322)):** `RenameField` migration `0037_rename_node_id_meshtastic_node_id` (+ `0038` help_text alters); `ObservedNode` / `ManagedNode` field + CHECK constraint; serializers, views (`lookup_field=meshtastic_node_id`, `lookup_url_kwarg=node_id`), admin, packets ingest auth, stats/traceroute/dx/mesh_monitoring/ws; `openapi.yaml` JSON field rename; unit tests (`571` passed locally after test-fix commit); `tests/integration/` JSON assertions updated
  - **bot:** No payload change (node upsert still uses JSON `id`; ingest URL path `<int:node_id>` unchanged)
  - **ui ([#268](https://github.com/pskillen/meshflow-ui/pull/268)):** `ObservedNode` / `ManagedNode` types and all `.meshtastic_node_id` usages; Playwright fixtures; skill doc `working_directory` note (same commit stream as #268)
- **PRs:** [#322](https://github.com/pskillen/meshflow-api/pull/322) · [meshflow-ui#268](https://github.com/pskillen/meshflow-ui/pull/268)
- **Notes:** #310 closed via coordinated merge. URL path segment and Django kwarg remain `node_id` until a URL epic; MeshCore detail by int still blocked ([#318](https://github.com/pskillen/meshflow-api/issues/318)). Deploy api before or with ui.

### SP-04 — ObservedNode MT identity fields

- **Merged:** —
- **Branch:** `api-312/pskillen/meshcore-rename-sp04-observed-node-mt` (api, ui)
- **Delivered:**
  - **api ([#323](https://github.com/pskillen/meshflow-api/pull/323)):** `RenameField` migration `0039_rename_observednode_meshtastic_identity_fields`; model, `ObservedNodeSerializer`, admin, infrastructure filter (`meshtastic_role__in`), mesh monitoring eligibility/summary; `NodeInfoPacketService` copies `NodeInfoPacket.*` onto `ObservedNode.meshtastic_*`; `NodeSerializer` (feeder upsert) exposes `meshtastic_*` in responses and accepts legacy `hw_model` / `public_key` on request; `openapi.yaml` `ObservedNode`, `ObservedNodeSearch`, `ObservedNodeUpdate`; unit + integration test JSON keys; follow-up `8488fae` — `create_observed_node` legacy kwargs + two mesh_monitoring tests
  - **ui ([#270](https://github.com/pskillen/meshflow-ui/pull/270)):** `ObservedNode` type and components; test fixtures (incl. `coverageHeardGhosts.test.ts`)
- **Out of scope (unchanged):** `NodeInfoPacket` / `MtRawPacket` columns and NODEINFO ingest wire JSON (SP-05 skipped — models are Meshtastic-specific); bot `MeshNodeSerializer.to_api_dict` still sends `hw_model` / `public_key`; `node_id_str` → `display_id` (comment-only defer); optional later `mac_addr` → `meshtastic_mac_addr`
- **Notes:** Deploy api before or with ui. MeshCore ingest does not set `meshtastic_*` identity fields. Feeder upsert wire shape still uses `id` / `macaddr` / nested `user` (not the same as `ObservedNodeUpdate` schema keys).

### SP-05 — Packet wire fields

- **Merged:** —
- **Skipped:** 2026-05-19 — [#311](https://github.com/pskillen/meshflow-api/issues/311) closed without implementation
- **Rationale:** `MtRawPacket`, `NodeInfoPacket`, and related ingest serializers already live on Meshtastic-only models/tables; column names (`hw_model`, `from_int`, `port_num`, etc.) describe Meshtastic wire semantics and do not need a `meshtastic_` prefix. SP-04 copies `NodeInfoPacket` → `ObservedNode.meshtastic_*` at the domain boundary. Stored traceroute hop JSON and NODEINFO camelCase ingest payloads stay unchanged.
- **Plan:** [meshcore-rename-sp05-packet-wire.plan.md](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-sp05-packet-wire.plan.md) (not executed)

### SP-06 — Channels + constellation

- **Merged:** —
- **Notes:**

### SP-07 — Text messages

- **Merged:** —
- **Notes:**

### SP-08 — Metrics columns

- **Merged:** —
- **Notes:**

### SP-09 — UI branding

- **Merged:** —
- **Notes:**

### SP-10 — Bot local naming

- **Merged:** —
- **Notes:**

### SP-11 — Lookup `internal_id` (deferred)

- **Merged:** —
- **Notes:**

---

## Outstanding and observations

_Capture follow-ups so they are not lost between sub-plans. Remove or strike through items when resolved._

### SP-05 / #311 (skipped)

- [x] Close [#311](https://github.com/pskillen/meshflow-api/issues/311) — no `RenameField` on `MtRawPacket` / `NodeInfoPacket` / `PacketObservation`; keep ingest wire JSON as documented in OpenAPI NODEINFO schemas.
- [ ] **Rename index plan** — optional: mark SP-05 `skipped` in `IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md` (Cursor plans repo, not meshflow-api).

### SP-04 / #312 (in progress — carry-overs)

- [ ] Merge [#323](https://github.com/pskillen/meshflow-api/pull/323) and [ui#270](https://github.com/pskillen/meshflow-ui/pull/270); set SP-04 to `merged`.
- [ ] **`tests/integration/`** — assertions updated for `meshtastic_*` JSON keys; re-run against deployed API with migration `0039` applied (`pytest tests/integration/ -v`).
- [ ] **`meshtastic_hw_model` help_text** — field has no `help_text` (SP-02 gap); optional `nodes/0040` `AlterField` only.
- [ ] **`meshtastic_is_licensed` / `meshtastic_is_unmessagable` help_text** — still bare booleans on the model; optional labelling migration.
- [ ] **Bot node upsert** — `MeshNodeSerializer` still POSTs `hw_model` / `public_key`; API accepts via `NodeSerializer.to_internal_value` alias until SP-10 or a bot PR. Responses from upsert now return `meshtastic_*`.
- [ ] **External JSON consumers** — anything reading observed-node list/detail JSON for `hw_model`, `role`, `public_key`, `is_licensed`, `is_unmessagable` must switch to `meshtastic_*` (UI done in #270; bot ingest path unchanged).
- [ ] **Test factories** — `create_observed_node` accepts legacy kwargs `role`, `hw_model`, `public_key`, `is_licensed`, `is_unmessagable` as aliases (like SP-03 `node_id`); prefer `meshtastic_*` in new tests. CI initially missed `role=` in two mesh_monitoring tests — grep for old names when closing rename sub-plans.
- [ ] **OpenAPI prose** — `/nodes/observed-nodes/infrastructure/` description still says “whose role is infrastructure” (human text; filter is `meshtastic_role__in`). Optional tweak to “Meshtastic role”.
- [ ] **`POST /packets/{node_id}/nodes/`** — OpenAPI may not document legacy request keys `hw_model` / `public_key` on feeder upsert (behaviour: accepted, not returned).

### SP-03 / #310 (done — carry-overs)

- [x] Merge [#322](https://github.com/pskillen/meshflow-api/pull/322) and [ui#268](https://github.com/pskillen/meshflow-ui/pull/268); set SP-03 to `merged`.
- [ ] **`tests/integration/`** — `tests/integration/test_node_lifecycle.py` and related files updated for `meshtastic_node_id` in JSON; re-run against a deployed API with migration `0037` applied (`pytest tests/integration/ -v`).
- [ ] **URL path names unchanged** — OpenAPI path params still named `node_id` on `/nodes/observed-nodes/{node_id}/`, `/packets/{node_id}/ingest/`, `/stats/nodes/{node_id}/*`, etc.; only response/request **body** fields renamed. Optional later epic: rename path param to `meshtastic_node_id` (Django kwarg can stay `node_id` via `lookup_url_kwarg`).
- [ ] **Bulk / admin request keys** — `APIKeyViewSet.add_node` and device/environment metrics bulk may still accept `node_id` / `node_ids` in request bodies (intentional for feeder nodenums); confirm OpenAPI documents `meshtastic_node_id` vs legacy names consistently.
- [ ] **Stored traceroute wire JSON** — `AutoTraceRoute.route` / `route_back` hop arrays still use Meshtastic wire key `node_id`; enriched API fields (`route_nodes`, heatmap nodes, etc.) use `meshtastic_node_id`. Intentionally unchanged (SP-05 skipped).
- [ ] **`NodeInfoPacket.node_id`** — packet model hex id field unchanged (not `ObservedNode`).
- [ ] **`Position.node_id` FK** — Django FK column on `Position` still named `node_id` (points at `ObservedNode.internal_id`); only ORM joins on numeric id use `node__meshtastic_node_id`.
- [ ] **Test factories** — `create_observed_node` / `create_managed_node` accept legacy kwarg `node_id` as alias for `meshtastic_node_id` (conftest); SP-04 adds aliases for `role`, `hw_model`, `public_key`, `is_licensed`, `is_unmessagable` → `meshtastic_*`. New tests should prefer `meshtastic_*` names.
- [ ] **Migration numbering on `main`** — SP-02 landed `nodes/0037` help_text alters on some branches; SP-03 adds `0037_rename_node_id_meshtastic_node_id` + `0038` help_text. After both merge, verify single linear chain on `main` (no duplicate `0037` filenames).
- [ ] **External clients** — any scripts, Grafana, or third-party consumers of observed/managed node JSON still sending/reading `node_id` need updating (bot unchanged; UI done in #268).
- [ ] **meshflow-ui nav parity** — separate from SP-03: [ui#269](https://github.com/pskillen/meshflow-ui/issues/269) (Meshtastic/MeshCore sidebar sections, shared map/list).

### SP-02 / #309 (done — carry-overs)

- [x] Merge coordinated PRs [#321](https://github.com/pskillen/meshflow-api/pull/321), [bot#96](https://github.com/pskillen/meshflow-bot/pull/96), [ui#267](https://github.com/pskillen/meshflow-ui/pull/267); set SP-02 to `merged`.
- [ ] **`ObservedNode.internal_id` in meshflow-ui** — still typed as `number` in `src/lib/models.ts`; OpenAPI is `string` / `uuid` ([#321](https://github.com/pskillen/meshflow-api/pull/321) did not change TS types). Fix in a UI contract pass or SP-04+.
- [ ] **OpenAPI `latest_air_quality_metrics` / `latest_health_metrics` / `latest_host_metrics`** — no explicit Meshtastic-only descriptions on `ObservedNode` (only position, device, environment, power were annotated in #321).
- [x] **`hw_model`, `is_licensed`, `is_unmessagable`** — renamed to `meshtastic_*` in SP-04 ([#312](https://github.com/pskillen/meshflow-api/issues/312)); `meshtastic_hw_model` still lacks `help_text` (optional `AlterField` follow-up).
- [ ] **Metric serializer docstrings** — only `DeviceMetricsSerializer` got an MT protocol note; `EnvironmentMetricsSerializer` / `PowerMetricsSerializer` / etc. unchanged.
- [ ] **`/nodes/environment-metrics-bulk/`** — still lacks MT-only description (same gap as SP-01; optional OpenAPI-only PR).
- [ ] **`meshcore_packets/0002`** — index renames only apply where `0001_initial` created `meshcore_raw_*` index names; skip or fix manually on DBs that diverged.

### SP-01 / #308 (done — carry-overs)

- [x] Merge [#320](https://github.com/pskillen/meshflow-api/pull/320); SP-01 `merged`.
- [ ] Reconcile SP-01 OpenAPI paths with SP-03 body field names where both touch the same operations (e.g. observed-node detail schema now has `meshtastic_node_id` in #322).

### Deferred to other tickets (from SP-01 / SP-03)

- [ ] **API v1 ingest retirement** — [#319](https://github.com/pskillen/meshflow-api/issues/319); bot [#95](https://github.com/pskillen/meshflow-bot/issues/95) (`StorageAPIWrapper._get_url()` `api_version == 1`). After bot defaults to v2, consider removing deprecated `POST /raw-packet/` from OpenAPI unless a compat redirect remains.
- [ ] **ObservedNode detail by `internal_id`** — SP-11 [#318](https://github.com/pskillen/meshflow-api/issues/318); until then MeshCore clients use `GET /nodes/observed-nodes/?protocol=meshcore` (documented on detail route).

### Doc drift spotted during SP-01 (not fixed in #320; partially addressed in #322)

- [ ] **`/nodes/environment-metrics-bulk/`** — same Meshtastic `node_ids` semantics as `device-metrics-bulk`, but SP-01 did not add an MT-only description there (optional small OpenAPI follow-up).
- [ ] **Nested `positions/`** (and other observed-node sub-routes using `{node_id}`) — path param description still says numeric `node_id`; response bodies use `meshtastic_node_id` after #322.
- [ ] **`ObservedNodeSearch` schema** — `ObservedNodeSearchSerializer` returns `internal_id` (UUID); OpenAPI search response schema still omits it.
- [ ] **meshflow-ui** — `ObservedNode.internal_id` typed as `number` in `src/lib/models.ts`; should be `string` when UI picks up OpenAPI contract (not done in SP-02 or #268 — see SP-02 carry-overs above).

### Conventions / process

- No operation in `openapi.yaml` uses `tags: [Packets]`; only the global tag definition was clarified — legacy name is documentation-only.
- OpenAPI operation descriptions link to GitHub issues (e.g. #318); fine for repo readers, may not render in all Swagger UIs.
