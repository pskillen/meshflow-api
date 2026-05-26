# Packet statistics (MeshCore snapshots) — outstanding

Items **skipped**, **incomplete**, or **discovered during execution** — not the [#329](https://github.com/pskillen/meshflow-api/issues/329) plan’s future phases.

**Tracking:** [meshflow-api#329](https://github.com/pskillen/meshflow-api/issues/329)

---

## Documentation

- [x] **RECENCY.md** § `stats/` — link to [packet-stats/README.md](README.md)
- [x] **features/README.md** — packet-stats under Stats & dashboard

## Implementation (#329 — API Task 2)

- [ ] Hourly `mc_packet_volume`, `mc_online_nodes`, `mc_new_nodes` collectors
- [ ] OpenAPI `stat_type` enum extension
- [ ] Unit tests mirroring `stats/tests/test_tasks.py`
- [ ] (Optional) `recent_counts?protocol=` for main dashboard MT/MC table

## Implementation (#329 — UI Task 3, meshflow-ui)

See plan § Task 3: main dashboard overlay, protocol dashboards, nav reorder (MC Managed nodes under Nodes; no MC traceroutes).

## Bug (fix in #329 PR)

- [ ] [#365](https://github.com/pskillen/meshflow-api/issues/365) — MT `online_nodes` / `new_nodes` snapshots must filter `ObservedNode` to `protocol=MESHTASTIC` (tracked in plan + #329)
