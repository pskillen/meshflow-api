# MeshCore / multi-protocol documentation

Cross-repo MeshCore work is tracked on GitHub epics [#264](https://github.com/pskillen/meshflow-api/issues/264) (Phase 0), [#265](https://github.com/pskillen/meshflow-api/issues/265) (Phase 1), [#266](https://github.com/pskillen/meshflow-api/issues/266) (Phase 2), [#267](https://github.com/pskillen/meshflow-api/issues/267) (Phase 3).

**Progress and follow-ups** are split by phase (not one monolithic file):

| Phase | Progress | Outstanding (skipped / incomplete / discovered in flight) |
| --- | --- | --- |
| **0** — bot seam, capture, ADRs | [phase-0-progress.md](./phase-0-progress.md) | [phase-0-outstanding.md](./phase-0-outstanding.md) |
| **1** — MC ingestion MVP | [phase-1-progress.md](./phase-1-progress.md) | [phase-1-outstanding.md](./phase-1-outstanding.md) |
| **2** — parity, rename track, position/text | [phase-2-progress.md](./phase-2-progress.md) | [phase-2-outstanding.md](./phase-2-outstanding.md) |
| **3** — traceroute / path parity ([#267](https://github.com/pskillen/meshflow-api/issues/267)) | [phase-3-progress.md](./phase-3-progress.md) | [phase-3-outstanding.md](./phase-3-outstanding.md) |
| **ManagedNode identity** ([#362](https://github.com/pskillen/meshflow-api/issues/362)) | [managed-node-identity-progress.md](./managed-node-identity-progress.md) | [managed-node-identity-outstanding.md](./managed-node-identity-outstanding.md) |
| **Feeder enrollment** ([#293](https://github.com/pskillen/meshflow-ui/issues/293)) | [enrollment-progress.md](./enrollment-progress.md) | [enrollment-outstanding.md](./enrollment-outstanding.md) |
| **Passive packet path** (Phase 3 slice) | [packet-path-tracing/packet-path-tracing-progress.md](./packet-path-tracing/packet-path-tracing-progress.md) | [packet-path-tracing/packet-path-tracing-outstanding.md](./packet-path-tracing/packet-path-tracing-outstanding.md) |

**Agent convention:** [progress-tracking skill](../../../.cursor/skills/progress-tracking/SKILL.md) — update progress/outstanding at plan breakpoints and before PRs.

**Feature guides** (how-to, not phase status):

- [feeder-bootstrap.md](./feeder-bootstrap.md) — first MC feeder + API key + `mc_pubkey`
- [text-message-channels.md](./text-message-channels.md) — Phase 2.2 text + channels (device → API sync, apply-to-radio, ops troubleshooting)
- [packet-path-tracing/](./packet-path-tracing/) — proposed passive MC packet path subsystem (capture, resolution, Neo4j, realtime/history UI)
- [../node-lifecycle/node-claims-meshcore.md](../node-lifecycle/node-claims-meshcore.md) — ownership claims via contact/DM proof

**Recent follow-up (post–#295 / staging):** see [phase-2-progress.md](./phase-2-progress.md) § “Feeder identity & apply fixes” and [phase-2-outstanding.md](./phase-2-outstanding.md) § “Phase 2.2 — staging & ops”.

**Related (meshflow-api)**

- Packet ingest ADRs: [../packet-ingestion/adr/](../packet-ingestion/adr/)
- MC field reference: [../packet-ingestion/MESHCORE_PACKET_FIELDS.md](../packet-ingestion/MESHCORE_PACKET_FIELDS.md)
- Sample JSON: [../../packets/meshcore/](../../packets/meshcore/)

**Rename sub-plans** (Phase 2 / [#307](https://github.com/pskillen/meshflow-api/issues/307)): index in `IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md` — status lives in [phase-2-progress.md](./phase-2-progress.md) and [phase-2-outstanding.md](./phase-2-outstanding.md).

**Convention for contributors**

- Update the **progress** file for the phase you are closing out (concrete paths, PR/issue links, env vars).
- Add items to **outstanding** only when work was skipped, left incomplete, or discovered during execution — not by copying future epic/plan checklists.
