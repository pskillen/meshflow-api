# MeshCore feeder enrollment — progress

**Tracking:** [meshflow-ui#293](https://github.com/pskillen/meshflow-ui/issues/293) (parent [meshflow-ui#291](https://github.com/pskillen/meshflow-ui/issues/291))  
**Plan:** `.cursor/plans/mc_managed_node_enrollment_f7aceb8d.plan.md`  
**Repos:** meshflow-api, meshflow-ui (meshflow-bot docs only if copy drift found)

**Prerequisite:** [managed-node-identity-progress.md](./managed-node-identity-progress.md) ([#362](https://github.com/pskillen/meshflow-api/issues/362)) merged and deployed before UI enrollment E2E.

---

## Overall status

**Status:** Not started (blocked on #362 API contract)

---

## Already done (pre-enrollment)

| Area | Status | Links |
| --- | --- | --- |
| Claim MC observed node | Complete | [meshflow-ui#292](https://github.com/pskillen/meshflow-ui/issues/292), `ClaimNode.tsx` |
| Ingest / feeder auth / channel sync | Complete | `test_feeder_identity.py`, feeder-bootstrap |
| Post-enroll MC settings (partial) | In repo | `NodeSettings.tsx` — channels, flood interval |

---

## Planned slices (from plan)

| Slice | Status | Repo |
| --- | --- | --- |
| API MC create + `internal_id` CRUD + api-key link | Not started | meshflow-api — **do not re-implement #362 shims** |
| UI `SetupManagedNode` MC branch | Not started | meshflow-ui |
| UI API client (`internal_id`, pubkey create) | Not started | meshflow-ui |
| `BotSetupInstructions` MC + v3 (#296, #295) | Not started | meshflow-ui |
| feeder-bootstrap.md wizard-first | Not started | meshflow-api |
| Manual E2E on staging | Not started | |

---

## Next

1. Complete and merge [#362](https://github.com/pskillen/meshflow-api/issues/362); deploy API.
2. API enrollment PR (`ui-293/.../managed-node-enrollment-api`) — identity work only if not already in #362.
3. UI wizard PR; update this file before each PR.
