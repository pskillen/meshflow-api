# MeshCore packet statistics (planned)

**Status:** Not implemented — design target for [#329](https://github.com/pskillen/meshflow-api/issues/329). Use [meshtastic.md](meshtastic.md) as the template for behaviour and JSON shapes.

## Goal

Hourly **MeshCore** packet / node statistics with the same operational model as Meshtastic: Celery beat at **:05 UTC** records the previous completed hour into `StatsSnapshot`, exposed via `GET /api/stats/snapshots/` for dashboard charts.

MeshCore ingest models: [`Meshflow/meshcore_packets/`](../../../Meshflow/meshcore_packets/) (`MeshCoreRawPacket`, `MeshCorePacketObservation`). Observed nodes use `protocol=MESHCORE` and `mc_pubkey` on [`ObservedNode`](../../../Meshflow/nodes/models.py).

## Planned snapshot types (proposed)

Prefix **`mc_`** on `stat_type` (no schema migration; extends OpenAPI enum):

| `stat_type` | Scope (MT parity) | Data source (intended) |
| --- | --- | --- |
| `mc_packet_volume` | Global only | `MeshCoreRawPacket.first_reported_time` in hour bucket; `by_type` from `MeshCorePayloadType` (`advert`, `channel_text`, `contact_text`, `raw`) |
| `mc_online_nodes` | Global + per-constellation | Global: `ObservedNode` `protocol=MESHCORE`, `last_heard`; constellation: distinct `from_pubkey` on `MeshCorePacketObservation` by feeder constellation |
| `mc_new_nodes` | Global + per-constellation | `ObservedNode` `protocol=MESHCORE` + `created_at` (delta / backfill same rules as MT) |

**Celery:** extend existing `collect_stats_snapshots` / `backfill_stats_snapshots` (single `run_id` per hour).

**Out of scope for #329:** live `GET /api/stats/global/` MeshCore aggregates; meshflow-ui protocol toggle; blending MT+MC in one chart without explicit `stat_type`.

## What exists today (not snapshots)

- **Managed-node live status** — packet counts in last 2 h / 24 h on `GET /api/nodes/managed-nodes/?include=status` (annotations on MC feeders). Documented under [meshcore phase-2-progress](../meshcore/phase-2-progress.md); separate from hourly `StatsSnapshot`.
- **Ingest** — [`meshcore_packets`](../packet-ingestion/MESHCORE_PACKET_FIELDS.md) populates raw packets and observations used by future collectors.

## UI (follow-up)

Dashboard [`MeshStatsSection`](https://github.com/pskillen/meshflow-ui/blob/main/src/components/MeshStatsSection.tsx) hardcodes `stat_type=packet_volume`. After API ships `mc_*` types, a UI issue can add protocol selection or separate MC charts.

## References

- Tracking: [#329](https://github.com/pskillen/meshflow-api/issues/329), epic [#266](https://github.com/pskillen/meshflow-api/issues/266)
- Progress: [packet-stats-progress.md](packet-stats-progress.md)
