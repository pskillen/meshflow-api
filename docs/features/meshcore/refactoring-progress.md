# MeshCore / multi-protocol — refactoring progress (rename & labelling)

Living tracker for the [rename audit index](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md) sub-plans.

**Sub-plans:** `IdeaProjects/MeshFlow/.cursor/plans/` · **Sub-epic:** [#307](https://github.com/pskillen/meshflow-api/issues/307) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266))

**Update this file in every PR** that executes a sub-plan (even doc-only PRs).

**Convention**

- Status: `not_started` | `in_progress` | `merged` | `deferred`
- Link the GitHub issue when filed; link the PR when opened.
- After merge, set status to `merged` and note the merge commit or PR number.

---

## Sub-plan index

| ID | Sub-plan | Repos | PRs | Status | Issue | PR |
|----|----------|-------|-----|--------|-------|-----|
| SP-01 | OpenAPI contract docs | api | 1 | in_progress | [#308](https://github.com/pskillen/meshflow-api/issues/308) | [#320](https://github.com/pskillen/meshflow-api/pull/320) |
| SP-02 | Comment-only labelling | api, bot, ui | 1–3 | in_progress | [#309](https://github.com/pskillen/meshflow-api/issues/309) | [#321](https://github.com/pskillen/meshflow-api/pull/321) · [bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [ui#267](https://github.com/pskillen/meshflow-ui/pull/267) |
| SP-03 | `node_id` → `meshtastic_node_id` | api, bot, ui | 1 (coordinated) | in_progress | [#310](https://github.com/pskillen/meshflow-api/issues/310) | [#322](https://github.com/pskillen/meshflow-api/pull/322) · [ui#268](https://github.com/pskillen/meshflow-ui/pull/268) |
| SP-04 | ObservedNode MT identity fields | api, ui | 1 | not_started | [#312](https://github.com/pskillen/meshflow-api/issues/312) | |
| SP-05 | MtRawPacket wire + observations | api | 1 | not_started | [#311](https://github.com/pskillen/meshflow-api/issues/311) | |
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

- **Merged:** — (awaiting [#320](https://github.com/pskillen/meshflow-api/pull/320); head `918f7f8`)
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

- **Merged:** —
- **Branch:** `api-309/pskillen/meshcore-rename-sp02-comments` (api, bot, ui)
- **Delivered (doc-only, no migrations / JSON renames):**
  - **api:** `ObservedNode` help_text (`mac_addr`, names, `public_key`, `role`); `NodeLatestStatus.inferred_max_hops`; `RoleSource` / `LocationSource` module docstrings; `BaseNodeItem` (unchanged, already labelled); `TextMessage.original_packet` help_text; serializer/view docstrings; OpenAPI `ObservedNode`, nested `latest_*`, `TextMessage`, list `GET /nodes/observed-nodes/`
  - **bot:** `src/radio/events.py` (`portnum`, `from_id`/`to_id` with `mc:` examples, hops); `interface.py` (`local_nodenum`, `send_traceroute` MT-only); `StorageAPI.py` v2 Meshtastic ingest vs `/api/meshcore/packets/ingest/`
  - **ui:** `src/lib/models.ts` JSDoc on `ObservedNode` + MT-only nested metrics; `meshtastic-api.ts` list/detail comments for mixed resource + `protocol` filter
- **PRs:** [#321](https://github.com/pskillen/meshflow-api/pull/321) · [meshflow-bot#96](https://github.com/pskillen/meshflow-bot/pull/96) · [meshflow-ui#267](https://github.com/pskillen/meshflow-ui/pull/267)
- **Notes:** Closes #309 when all three PRs merge. Detail route remains Meshtastic `node_id` ([#318](https://github.com/pskillen/meshflow-api/issues/318)).

### SP-03 — `meshtastic_node_id`

- **Merged:** —
- **Branch:** `api-310/{author}/meshcore-rename-sp03-meshtastic-node-id` (api, bot, ui)
- **Delivered:**
  - **api:** `RenameField` migration `0037_rename_node_id_meshtastic_node_id`; `ObservedNode` / `ManagedNode` field + CHECK constraint; serializers, views (`lookup_field` + `lookup_url_kwarg=node_id`), admin, packets ingest auth, stats/traceroute/dx/ws call sites; `openapi.yaml` JSON field rename; integration/unit tests
  - **bot:** No payload change (node upsert still uses JSON `id`; ingest URL path `<int:node_id>` unchanged)
  - **ui:** `ObservedNode` / `ManagedNode` types and all `.meshtastic_node_id` usages; Playwright fixtures
- **PRs:** [#322](https://github.com/pskillen/meshflow-api/pull/322) · [meshflow-ui#268](https://github.com/pskillen/meshflow-ui/pull/268)
- **Notes:** URL path segment and Django kwarg remain `node_id` until a URL epic; MeshCore detail by int still blocked ([#318](https://github.com/pskillen/meshflow-api/issues/318)). Closes #310 when coordinated PRs merge.

### SP-04 — ObservedNode MT identity fields

- **Merged:** —
- **Notes:**

### SP-05 — Packet wire fields

- **Merged:** —
- **Notes:**

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

### SP-01 / #320 (in flight)

- [ ] Merge [#320](https://github.com/pskillen/meshflow-api/pull/320); then set SP-01 status to `merged`, record merge commit SHA, and confirm #308 closed.
- [ ] PR was **open** / merge blocked at last check (2026-05-19) — confirm CI/review before merge.

### Deferred to other tickets (from SP-01)

- [ ] **API v1 ingest retirement** — [#319](https://github.com/pskillen/meshflow-api/issues/319); bot [#95](https://github.com/pskillen/meshflow-bot/issues/95) (`StorageAPIWrapper._get_url()` `api_version == 1`). After bot defaults to v2, consider removing deprecated `POST /raw-packet/` from OpenAPI unless a compat redirect remains.
- [ ] **ObservedNode detail by `internal_id`** — SP-11 [#318](https://github.com/pskillen/meshflow-api/issues/318); until then MeshCore clients use `GET /nodes/observed-nodes/?protocol=meshcore` (documented on detail route).

### Doc drift spotted during SP-01 (not fixed in #320)

- [ ] **`/nodes/environment-metrics-bulk/`** — same Meshtastic `node_ids` semantics as `device-metrics-bulk`, but SP-01 did not add an MT-only description there (optional small OpenAPI follow-up).
- [ ] **Nested `positions/`** (and other observed-node sub-routes using `{node_id}`) — same MT path param as metrics; only metrics routes got explicit MT notes in #320.
- [ ] **`ObservedNodeSearch` schema** — `ObservedNodeSearchSerializer` returns `internal_id` (UUID); OpenAPI search response schema still omits it.
- [ ] **meshflow-ui** — `ObservedNode.internal_id` typed as `number` in `src/lib/models.ts`; should be `string` when UI picks up OpenAPI contract (likely SP-02+ or a UI pass, out of api-only SP-01).

### Conventions / process

- No operation in `openapi.yaml` uses `tags: [Packets]`; only the global tag definition was clarified — legacy name is documentation-only.
- OpenAPI operation descriptions link to GitHub issues (e.g. #318); fine for repo readers, may not render in all Swagger UIs.
