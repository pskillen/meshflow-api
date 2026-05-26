# MeshCore feeder enrollment — progress

**Tracking:** [meshflow-ui#293](https://github.com/pskillen/meshflow-ui/issues/293) (parent [meshflow-ui#291](https://github.com/pskillen/meshflow-ui/issues/291))  
**Plan:** `.cursor/plans/mc_managed_node_enrollment_f7aceb8d.plan.md`  
**Repos:** meshflow-api (docs), meshflow-ui (wizard + instructions)

**Prerequisite:** [managed-node-identity-progress.md](./managed-node-identity-progress.md) ([#362](https://github.com/pskillen/meshflow-api/issues/362) / [PR #363](https://github.com/pskillen/meshflow-api/pull/363)) — merged on `main`; deploy with migration `0050_managednode_protocol_identity` before UI E2E.

---

## Overall status

**Status:** Complete (implementation); staging E2E verification pending operator

---

## Already done (pre-enrollment)

| Area | Status | Links |
| --- | --- | --- |
| Claim MC observed node | Complete | [meshflow-ui#292](https://github.com/pskillen/meshflow-ui/issues/292), `ClaimNode.tsx` |
| ManagedNode protocol identity (#362) | Complete | `internal_id` CRUD, `mc_pubkey`, API key `managed_node_internal_id`, `linked_managed_nodes` |
| Ingest / feeder auth / channel sync | Complete | `test_feeder_identity.py`, [feeder-bootstrap.md](./feeder-bootstrap.md) |
| Post-enroll MC settings | Complete | `NodeSettings.tsx` — channels, flood interval, apply-to-radio |

---

## Enrollment slices (this initiative)

| Slice | Status | Repo / notes |
| --- | --- | --- |
| API MC create + `internal_id` CRUD + api-key link | Complete (#362) | meshflow-api — not re-implemented |
| Optional API pre-fill `mc_pubkey` on create | Skipped | UI sends pubkey from claim; no server pre-fill PR |
| UI `SetupManagedNode` MC branch | Complete | `SetupManagedNode.tsx`, `managed-node-enrollment.ts` |
| UI API client (`internal_id`, pubkey create) | Complete | `meshflow-api.ts`, `models.ts`, `NodeSettings.tsx`, `ApiKeysPage.tsx` |
| `BotSetupInstructions` MC + v3 (#296, #295) | Complete | `BotSetupInstructions.tsx`, `STORAGE_API_VERSION=3` |
| feeder-bootstrap.md wizard-first | Complete | Primary path: UI wizard; admin fallback |
| Manual E2E on staging | Pending | Operator: claim → wizard → bot ingest → MC map pin |

---

## Next

1. Deploy meshflow-api with migration `0050` if not already on target env.
2. Ship meshflow-ui PR(s) for #293 / #296 / #295 (branch `ui-293/.../meshcore-feeder-enrollment-wizard`).
3. Run staging E2E checklist in plan (claim MC → Node Settings → wizard → bot `mc-channel-sync` + ingest).
