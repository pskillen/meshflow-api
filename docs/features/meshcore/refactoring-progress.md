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
| SP-01 | OpenAPI contract docs | api | 1 | in_progress | [#308](https://github.com/pskillen/meshflow-api/issues/308) | |
| SP-02 | Comment-only labelling | api, bot, ui | 1–3 | not_started | [#309](https://github.com/pskillen/meshflow-api/issues/309) | |
| SP-03 | `node_id` → `meshtastic_node_id` | api, bot, ui | 1 (coordinated) | not_started | [#310](https://github.com/pskillen/meshflow-api/issues/310) | |
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

- **Merged:** —
- **Notes:** OpenAPI drift fix (#308): `/packets/{node_id}/ingest|nodes/`; `ObservedNode.internal_id` UUID; Meshtastic-only notes on device-metrics bulk, nested observed-node metrics, `/stats/nodes/{node_id}/*`; legacy **Packets** tag points to **Meshtastic packets**.

### SP-02 — Comment-only labelling

- **Merged:** —
- **Notes:**

### SP-03 — `meshtastic_node_id`

- **Merged:** —
- **Notes:**

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
