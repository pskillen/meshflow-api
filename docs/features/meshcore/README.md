# MeshCore / multi-protocol documentation

Cross-repo MeshCore work is tracked on GitHub epics [#264](https://github.com/pskillen/meshflow-api/issues/264) (Phase 0), [#265](https://github.com/pskillen/meshflow-api/issues/265) (Phase 1), [#266](https://github.com/pskillen/meshflow-api/issues/266) (Phase 2).

**Progress and follow-ups** are split by phase (not one monolithic file):

| Phase | Progress | Outstanding (skipped / incomplete / discovered in flight) |
| --- | --- | --- |
| **0** — bot seam, capture, ADRs | [phase-0-progress.md](./phase-0-progress.md) | [phase-0-outstanding.md](./phase-0-outstanding.md) |
| **1** — MC ingestion MVP | [phase-1-progress.md](./phase-1-progress.md) | [phase-1-outstanding.md](./phase-1-outstanding.md) |
| **2** — parity, rename track, position/text | [phase-2-progress.md](./phase-2-progress.md) | [phase-2-outstanding.md](./phase-2-outstanding.md) |

**Feature guides** (how-to, not phase status):

- [feeder-bootstrap.md](./feeder-bootstrap.md) — first MC feeder + API key + `mc_pubkey`
- [text-message-channels.md](./text-message-channels.md) — Phase 2.2 text + channels (device → API sync, apply-to-radio, ops troubleshooting)

**Recent follow-up (post–#295 / staging):** see [phase-2-progress.md](./phase-2-progress.md) § “Feeder identity & apply fixes” and [phase-2-outstanding.md](./phase-2-outstanding.md) § “Phase 2.2 — staging & ops”.

**Related (meshflow-api)**

- Packet ingest ADRs: [../packet-ingestion/adr/](../packet-ingestion/adr/)
- MC field reference: [../packet-ingestion/MESHCORE_PACKET_FIELDS.md](../packet-ingestion/MESHCORE_PACKET_FIELDS.md)
- Sample JSON: [../../packets/meshcore/](../../packets/meshcore/)

**Rename sub-plans** (Phase 2 / [#307](https://github.com/pskillen/meshflow-api/issues/307)): index in `IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md` — status lives in [phase-2-progress.md](./phase-2-progress.md) and [phase-2-outstanding.md](./phase-2-outstanding.md).

**Convention for contributors**

- Update the **progress** file for the phase you are closing out (concrete paths, PR/issue links, env vars).
- Add items to **outstanding** only when work was skipped, left incomplete, or discovered during execution — not by copying future epic/plan checklists.
