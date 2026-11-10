# MeshCore packet statistics

Hourly **MeshCore** packet and node statistics with the same operational model as Meshtastic: Celery beat at **:05 UTC** records the previous completed hour into `StatsSnapshot` (in `stats.tasks`), exposed via `GET /api/stats/snapshots/` for dashboard charts. [meshtastic.md](meshtastic.md) is the reference for behaviour and JSON shapes.

MeshCore ingest models: [`Meshflow/meshcore_packets/`](../../../Meshflow/meshcore_packets/) (`MeshCoreRawPacket`, `MeshCorePacketObservation`). Observed nodes use `protocol=MESHCORE` and `mc_pubkey` on [`ObservedNode`](../../../Meshflow/nodes/models.py).

## Snapshot types

Prefix **`mc_`** on `stat_type`:

| `stat_type` | Scope | Data source |
| --- | --- | --- |
| `mc_packet_volume` | Global only | `MeshCoreRawPacket.first_reported_time` in the hour bucket; `by_type` from `MeshCorePayloadType` (`advert`, `channel_text`, `contact_text`, `raw`) |
| `mc_online_nodes` | Global + per-constellation | Distinct senders heard in the `ONLINE_NODE_WINDOW_HOURS` window centred on `recorded_at` (2 h: `[H - 1h, H + 1h]`): global from `MeshCoreRawPacket.first_reported_time`, constellation from `MeshCorePacketObservation.rx_time` by feeder constellation. A sender is its 12-hex pubkey prefix (`from_pubkey[:12]`, else `from_pubkey_prefix`), because `from_pubkey` is null on prefix-only packets that still advance `last_heard`. Same cut-over and `--rewrite-online` backfill as MT, see [meshtastic.md](meshtastic.md#online_nodes) |
| `mc_new_nodes` | Global + per-constellation | `ObservedNode` `protocol=MESHCORE` + `created_at` (delta and backfill follow the MT rules) |

**Daily rollup:** `GET /api/stats/snapshots/?bucket=1d` works for `mc_*` types the same way as for MT (gauges averaged, flows summed; needs `stat_type` and `recorded_at_after`). See [meshtastic.md](meshtastic.md#stored-snapshots) for the contract. If the bounds are not UTC midnight, the first and last days are partial (`value.samples` < 24).

**Celery:** `collect_stats_snapshots` and `backfill_stats_snapshots` record both protocols under a single `run_id` per hour.

## Live stats

There are no MeshCore live stats endpoints; `/api/stats/global/` and the per-node endpoints are Meshtastic only.

## Managed-node live status

Packet counts for the last 2 h and 24 h are on `GET /api/nodes/managed-nodes/?include=status` (annotations on MeshCore feeders). This is separate from the hourly `StatsSnapshot`.

## UI consumers

- `MeshStatsSection` reads the `mc_*` types on the MeshCore dashboard and overlays both protocols on Home.
- `RightNowBand` reads `recent_counts?protocol=`.

## References

- Ingest fields: [`meshcore_packets`](../packet-ingestion/MESHCORE_PACKET_FIELDS.md).
