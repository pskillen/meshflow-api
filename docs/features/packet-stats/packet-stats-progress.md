# Packet statistics (MeshCore snapshots) — progress

**Tracking:** [meshflow-api#329](https://github.com/pskillen/meshflow-api/issues/329) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266))  
**Plan:** `.cursor/plans/#329_mc_stats_snapshots_94705979.plan.md`  
**Repos:** meshflow-api, meshflow-ui

---

## Overall status

**Status:** Complete (pending merge + deploy)

**PR (API):** https://github.com/pskillen/meshflow-api/pull/366 — closes #329, #365

**PR (UI):** https://github.com/pskillen/meshflow-ui/pull/306

**Branch (API):** `api-329/pskillen/packet-stats-docs`

**Branch (UI):** `api-329/pskillen/mc-stats-ui`

---

## Task 1 — Document Meshtastic stats

**Status:** Complete

**Delivered**

- [docs/features/packet-stats/](README.md) hub + [meshtastic.md](meshtastic.md) + [meshcore.md](meshcore.md)
- RECENCY + features README cross-links

---

## Task 2 — API

**Status:** Complete (pending PR merge)

**Delivered**

- [#365](https://github.com/pskillen/meshflow-api/issues/365): `protocol=MESHTASTIC` on MT `online_nodes` / `new_nodes`
- `mc_packet_volume`, `mc_online_nodes`, `mc_new_nodes` collectors + backfill
- `recent_counts?protocol=` on observed nodes
- OpenAPI `stat_type` enum extended
- Tests: `Meshflow/stats/tests/test_mc_snapshots.py`

**Verify**

```bash
cd Meshflow && source ../venv/bin/activate
python -m pytest Meshflow/stats/ -v
```

---

## Task 3 — UI (meshflow-ui)

**Status:** Complete (pending PR)

**Delivered**

- Main `/` dashboard: MT+MC recent counts, overlaid Mesh Stats, node activity removed
- `/meshtastic/dashboard`, `/meshcore/dashboard`
- Nav: protocol dashboards first; MC Managed nodes under Nodes

---

## Next

1. Push API + UI branches; open PRs (closes #329, #365 on API).
2. Deploy API; run `backfill_stats_snapshots` for MC history.
3. Deploy UI after API.
