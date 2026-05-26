---
name: mf-feature-docs
description: >-
  How Meshflow documents features under docs/features/. Use when adding or
  updating feature docs, reverse-engineering behaviour for a ticket, or creating
  progress/outstanding logs for an initiative.
---

# Meshflow feature documentation

Canonical feature docs live under **`docs/features/<topic>/`** in **meshflow-api** (even when UI or bot code participates). Cross-cutting concerns stay in
**`docs/`** root (`RECENCY.md`, `ENV_VARS.md`, `permissions/`, `API.md`, `openapi.yaml`).

Read [progress-tracking](../../skills/progress-tracking/SKILL.md) when an initiative needs execution handoff files.

---

## Folder layout

| Pattern | When to use | Examples |
| --- | --- | --- |
| **`<topic>/README.md`** | Every feature area — hub page | `mesh-monitoring/README.md`, `packet-stats/README.md` |
| **Sibling deep dives** | One concern per file; keep README as map | `flow.md`, `permissions.md`, `meshtastic.md` |
| **`adr/`** | Irreversible or contested design choices | `packet-ingestion/adr/` |
| **`*-progress.md` / `*-outstanding.md`** | Multi-step plans, epics, or tickets spanning PRs | `phase-2-progress.md`, `packet-stats-progress.md` |
| **Phase files** | Large epics with numbered delivery | `meshcore/phase-1-progress.md` |

**Slug:** kebab-case directory name matching the product concept (`packet-stats`, `mesh-monitoring`, not Django app name unless they align).

**Do not** put the full plan backlog in `*-outstanding.md` — only debt discovered during execution (see progress-tracking skill).

---

## README hub template

Every feature README should open with **what problem it solves** (1–3 paragraphs), then:

1. **Implementation status** — table: area | status | notes (shipped / in progress / deferred).
2. **Documentation map** — table linking sibling docs.
3. **Concepts** — domain terms the reader needs before detail pages.
4. **Optional diagram** — mermaid sequence/state when flow is non-obvious.
5. **Cross-links** — `RECENCY.md` for time windows, `openapi.yaml` tag for HTTP, related features, parent GitHub epic/issue.

Stop at the feature boundary: ingestion README emits signals and points to downstream features; do not document traceroute completion inside packet-ingestion.

---

## Deep-dive page template

Use for `flow.md`, protocol-specific docs, etc.

| Section | Contents |
| --- | --- |
| **Purpose** | What this slice does vs the hub README |
| **Code anchors** | Django app paths, main modules (`Meshflow/stats/tasks.py`) |
| **Data sources** | Models, fields, filters (be precise — contributors should not re-read code line-by-line) |
| **Schedules / env** | Celery beat, env vars with defaults; link `docs/RECENCY.md` § app |
| **HTTP API** | Paths, auth (`AllowGuestReadOnly` vs JWT), query params; point to OpenAPI |
| **Consumers** | meshflow-ui hooks/components, bots, ops commands |
| **Known gaps** | Explicit TODOs, deferred protocol support, doc drift |
| **Related** | Other feature docs, issues |

Prefer **tables** for endpoints, snapshot types, and field shapes. Use **JSON examples** for `StatsSnapshot.value` and API payloads when shape matters.

---

## Progress and outstanding pair

Create both at **plan kickoff** if missing. Update **progress** when a PR/commit lands; update **outstanding** only for skipped scope or issues found while executing.

| File | Role |
| --- | --- |
| `*-progress.md` | Shipped slices, PR links, branch, verify commands, **Next** |
| `*-outstanding.md` | Checkboxes for discovered debt — not future plan phases |

Link both from the tracking GitHub issue and the Cursor plan **Progress tracking** section.

---

## Style conventions (inferred from existing docs)

- **British English** spelling in prose is fine; code identifiers stay as in repo.
- Link GitHub issues/PRs with full URLs: `[meshflow-api#329](https://github.com/pskillen/meshflow-api/issues/329)`.
- Use relative links between docs: `[meshtastic.md](meshtastic.md)`.
- Cite **concrete defaults** (e.g. “`:05` UTC”, “2 h window”) — they belong in feature docs *and* `RECENCY.md` for ops; feature doc explains *behaviour*, RECENCY is the quick index.
- When behaviour changes, update **feature doc**, **`RECENCY.md`** (if time-related), and **`openapi.yaml`** (if API contract changes).
- **Reverse-engineering ticket:** document *current* behaviour first in a protocol or mechanism doc; add `meshcore.md` (or a section) for planned parity before implementing.

---

## Index maintenance

When adding a new feature folder:

1. Add a row or subsection under [docs/features/README.md](../../../docs/features/README.md) **Features** (or **Cross-Cutting** if appropriate).
2. Add `docs/RECENCY.md` § if the feature introduces recency windows or periodic jobs.
3. For MeshCore work, add a row to [docs/features/meshcore/README.md](../../../docs/features/meshcore/README.md) when relevant.

---

## Anti-patterns

- Duplicating `openapi.yaml` field lists in full — summarize and link OpenAPI.
- One giant README with no map (split when > ~200 lines or multiple audiences).
- Outstanding file copied from the Cursor plan todo list.
- Documenting aspirational behaviour as shipped — use **Implementation status** and **Known gaps**.
