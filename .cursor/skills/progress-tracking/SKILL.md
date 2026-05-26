---
name: progress-tracking
description: >-
  Maintains progress and outstanding markdown logs for multi-step Meshflow plans
  and epics. Use when executing a Cursor plan, a multi-repo feature, or when the
  user asks to update progress/outstanding docs, hand off between agents, or
  before opening a PR for a large initiative.
---

# Progress tracking (Meshflow plans)

Persistent **progress** and **outstanding** files preserve execution state when context is lost, agents switch, or work spans multiple PRs. Follow this skill whenever a Cursor plan or epic has non-trivial scope (multi-commit, multi-repo, or high coordination risk).

**Reference examples (large epic):** [docs/features/meshcore/phase-2-progress.md](../../docs/features/meshcore/phase-2-progress.md), [phase-2-outstanding.md](../../docs/features/meshcore/phase-2-outstanding.md).

---

## Two files — distinct roles

| File | Purpose | Put here | Do **not** put here |
|------|---------|----------|---------------------|
| **`*-progress.md`** | What **shipped** or is **in flight** | Merged PRs, deploy notes, verification commands, env vars, concrete file paths | Future plan steps not started; raw checklists copied from the plan |
| **`*-outstanding.md`** | **Debt discovered during execution** | Skipped scope, incomplete merges, bugs found, follow-ups that block verification, doc drift | The plan’s upcoming phases; epic backlog that was never in scope for this initiative |

**Outstanding is not a second plan.** If work is scheduled but not started, it stays in the Cursor plan (or GitHub issue). Move an item to outstanding only when execution revealed it (missed, deferred mid-flight, or needs a later ticket).

---

## Where files live

Default under **`docs/features/<topic>/`** in the repo that owns most of the work (usually **meshflow-api** for API-heavy initiatives).

| Initiative | Progress | Outstanding |
|------------|----------|-------------|
| MeshCore phase epics | `phase-N-progress.md` | `phase-N-outstanding.md` |
| Focused plan (e.g. #362, enrollment) | `<slug>-progress.md` | `<slug>-outstanding.md` |

**Slug:** kebab-case from the plan name (e.g. `managed-node-identity`, `enrollment`).

For **multi-repo** work, one progress pair in meshflow-api is enough unless UI-only work needs `meshflow-ui/docs/...` (rare). Link sibling PRs from the api progress file.

Add a row to [docs/features/meshcore/README.md](../../docs/features/meshcore/README.md) when the work is MeshCore-related.

---

## When to read and update

### At plan start (required)

1. Read the linked **progress** and **outstanding** files if they exist.
2. If missing, create both from the templates below (initial progress = tracking issue, plan link, status **Not started** or **In progress**).
3. In the Cursor plan, add a **Progress tracking** section pointing at both files (see plan template).

### During execution (at logical breakpoints)

Update **progress** when:

- A commit or PR lands a coherent slice (match [meshflow-git-workflow](../meshflow-git-workflow/SKILL.md) atomic commits).
- Deploy order or env prerequisites change.
- A phase flips to **Complete** with PR/issue links.

Update **outstanding** when:

- You skip or narrow scope and need a follow-up ticket later.
- You discover a bug, doc error, or missing test during the ticket (not pre-planned work).
- Production verification is blocked on something outside the current PR.

**Cadence (use judgment):**

| Plan size | Typical updates |
|-----------|-----------------|
| Small (1 PR, &lt;5 files) | Once before opening PR |
| Medium (2–4 atomic commits) | After migration/API contract; before PR |
| Large / multi-repo | Per plan phase + before each PR |

**Always update progress before opening a PR** for initiatives that use this skill.

### At handoff

Leave progress with accurate **Status** lines, open PR URLs, branch names, and “**Next:**” for the successor agent.

---

## Progress file template

```markdown
# <Title> — progress

**Tracking:** [meshflow-api#NNN](https://github.com/pskillen/meshflow-api/issues/NNN) (and cross-links)
**Plan:** `.cursor/plans/<plan-file>.plan.md` or GitHub issue
**Repos:** meshflow-api, …

---

## Overall status

**Status:** Not started | In progress | Complete (pending deploy) | Complete

**Branch:** `api-NNN/<author>/<slug>` (per repo if applicable)

---

## <Phase or slice name>

**Status:** …
**PR:** …

**Delivered**

- …

**Deploy / verify**

- …

---

## Next

- …
```

Use checkboxes in **outstanding** only; progress sections use **Status** + bullet lists (see phase-2 examples).

---

## Outstanding file template

```markdown
# <Title> — outstanding

Items **skipped**, **incomplete**, or **discovered during execution** — not the plan’s future phases.

**Tracking:** same as progress file

---

## <area>

- [ ] …
- [x] … (closed when fixed; keep brief note or link to PR)

```

---

## Cursor plan integration

Every plan that uses progress tracking must include near the top:

```markdown
## Progress tracking

Read and update (per [progress-tracking](meshflow-api/.cursor/skills/progress-tracking/SKILL.md)):

- **Progress:** [docs/features/.../<slug>-progress.md](path)
- **Outstanding:** [docs/features/.../<slug>-outstanding.md](path)

Update both at logical breakpoints and **before each PR**.
```

When a plan depends on another (e.g. enrollment after #362), the dependent plan’s progress file should note **Prerequisite:** link to the other progress file and required merge/deploy state.

---

## GitHub issues

- Link progress/outstanding paths in the tracking issue body or a comment at kickoff.
- Do not duplicate the full progress log in the issue; the markdown files are canonical for agent handoff.
- Close outstanding items by linking the fixing PR or moving to a new issue if scope grew.

---

## Anti-patterns

- Copying the plan’s full todo list into outstanding.
- Marking plan phases “done” in progress without PR/commit evidence.
- Creating phase-0/1/2-style files for a single small ticket (one progress pair is enough).
- Letting progress go stale across multiple PRs without a **Next** section.
