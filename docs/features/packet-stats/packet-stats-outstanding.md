# Packet statistics (MeshCore snapshots) — outstanding

Items **skipped**, **incomplete**, or **discovered during execution** — not the [#329](https://github.com/pskillen/meshflow-api/issues/329) plan’s future phases.

**Tracking:** [meshflow-api#329](https://github.com/pskillen/meshflow-api/issues/329)

---

## Documentation

- [x] **RECENCY.md** § `stats/` — link to [packet-stats/README.md](README.md)
- [x] **features/README.md** — packet-stats under Stats & dashboard

## Implementation (#329 — API Task 2)

- [x] Hourly `mc_packet_volume`, `mc_online_nodes`, `mc_new_nodes` collectors
- [x] OpenAPI `stat_type` enum extension
- [x] Unit tests in `stats/tests/test_mc_snapshots.py`
- [x] `recent_counts?protocol=` for main dashboard MT/MC table

## Implementation (#329 — UI Task 3, meshflow-ui)

- [ ] Main dashboard overlay + protocol dashboard pages + nav (meshflow-ui PR)

## Bug (#365)

- [x] MT `online_nodes` / `new_nodes` filter `protocol=MESHTASTIC`
