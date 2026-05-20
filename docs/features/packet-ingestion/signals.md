# Packet post-processing signals

Neutral Django signals emitted by `packets` services after persistence. Feature apps subscribe in their own `receivers` modules and must not be imported from `packets/services/`.

## Ingest vs post-processing

1. **Ingest** (`PacketIngestView`) saves `MtRawPacket` + `PacketObservation`, then sends `packet_received` and the type-specific `*_packet_received` signal.
2. **`packets/receivers.py`** runs the matching `*PacketService` (`BasePacketService.process_packet`).
3. **Post-processing signals** (this document) fire from inside services for cross-app side effects.

## Signals

| Signal | Emitted from | kwargs | Typical subscribers |
|--------|----------------|--------|---------------------|
| `device_metrics_recorded` | `DeviceMetricsPacketService` | `observed_node`, `device_metrics`, `battery_level`, `reported_time` | `mesh_monitoring` (battery alerts) |
| `auto_traceroute_completed_from_packet` | `TraceroutePacketService` | `auto_tr`, `traceroute_packet`, `packet_observation`, `observer`, `from_node` | `dx_monitoring`, `mesh_monitoring`, `traceroute` (see wiring below) |
| `packet_from_node_processed` | `BasePacketService` (after `_process_packet`, **before** `last_heard` update) | `packet`, `observer`, `observation`, `from_node`, `previous_last_heard`, `from_node_created` | `dx_monitoring` (candidate detection) |
| `node_last_heard_advanced` | `BasePacketService._update_node_last_heard` | `observed_node`, `last_heard` | `mesh_monitoring` (clear presence flags) |

Definitions and docstrings: `Meshflow/packets/signals.py`.

## Multi-app handler order

Django runs receivers in connection order. For `auto_traceroute_completed_from_packet`, handlers are registered explicitly in **`packets/traceroute_completion_wiring.py`** (called from `PacketsConfig.ready()`):

1. `dx_monitoring` — distant-hop detection, then exploration row completion
2. `mesh_monitoring` — node-watch verification clear
3. `traceroute` — WebSocket status + Neo4j export enqueue

Feature modules define plain functions (not `@receiver` on that signal) to avoid duplicate connections.

`packet_from_node_processed` and `node_last_heard_advanced` use `@receiver` in the owning app; each has a single subscriber.

## Adding a new subscriber

1. Implement a handler in **your app** (`myapp/receivers.py`).
2. Import it from `myapp.apps.AppConfig.ready()` (or, for `auto_traceroute_completed_from_packet` only, add to `traceroute_completion_wiring.py` in the correct order).
3. Do **not** import your app from `packets/services/`.
4. Add tests that patch your handler or downstream services, not the packet service.

## Related

- [Packet ingestion overview](README.md)
- [Traceroute flow](../traceroute/flow.md)
- [Mesh monitoring flow](../mesh-monitoring/flow.md)
