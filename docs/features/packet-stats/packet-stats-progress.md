# Packet statistics (MeshCore snapshots) — progress

**Tracking:** [meshflow-api#329](https://github.com/pskillen/meshflow-api/issues/329) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266))  
**Plan:** `.cursor/plans/#329_mc_stats_snapshots_94705979.plan.md`  
**Repos:** meshflow-api (this work); meshflow-ui deferred

---

## Overall status

**Status:** In progress (Task 1 doc largely complete)

**Branch:** `api-329/pskillen/packet-stats-docs`

---

## Task 1 — Document Meshtastic stats

**Status:** In progress

**Delivered**

- Feature doc hub: [README.md](README.md)
- Reverse-engineered MT behaviour: [meshtastic.md](meshtastic.md)
- Feature-docs skill: [.cursor/rules/mf-feature-docs/SKILL.md](../../../.cursor/rules/mf-feature-docs/SKILL.md)
- Nascent MC plan doc: [meshcore.md](meshcore.md)
- Progress / outstanding pair (this file + [packet-stats-outstanding.md](packet-stats-outstanding.md))

**Still to do**

- Optional: trim duplicate #329 path `docs/features/stats/meshtastic_packets.md` if we standardize on `packet-stats/` only

**Cross-links done:** [RECENCY.md](../../RECENCY.md) § `stats/`, [features/README.md](../README.md), [phase-2-outstanding.md](../meshcore/phase-2-outstanding.md) (#329 doc path)

---

## Related bug

**[#365](https://github.com/pskillen/meshflow-api/issues/365)** — MT `online_nodes` / `new_nodes` include MC `ObservedNode` rows; fix in #329 implementation pass (see plan § MT protocol filter).

---

## Task 2 — MeshCore snapshot collectors

**Status:** Not started

**Delivered**

- _(none)_

**Deploy / verify**

- After implementation: `python -m pytest Meshflow/stats/ -v`
- Ops: `python manage.py backfill_stats_snapshots` for MC history

---

## Next

1. Finish Task 1 cross-links (RECENCY, features README).
2. Branch `api-329/<author>/mc-stats-snapshots` from `origin/main`.
3. Implement `mc_*` collectors in `stats/tasks.py` + tests + OpenAPI + update [meshcore.md](meshcore.md) when shipped.
