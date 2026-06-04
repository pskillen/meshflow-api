# MeshCore passive packet path

The MeshCore passive packet path subsystem turns ingested MeshCore packet route hints into realtime views, historical topology maps, Neo4j graph data, and router-importance stats.

It is intentionally separate from the Meshtastic `traceroute` subsystem:

- Meshtastic traceroute is an active probe lifecycle (`AutoTraceRoute`) with command dispatch, completion, timeout, and success/failure semantics.
- MeshCore passive packet path starts from passive packet observations (`MeshCorePacketObservation.path_hashes`) and aggregates observed path evidence.

## ADRs

- [ADR-0001 - MeshCore passive packet path subsystem](./adr/0001-meshcore-packet-path-tracing-subsystem.md)

## Progress tracking

- [Progress](./packet-path-tracing-progress.md) — what has shipped / is in flight
- [Outstanding](./packet-path-tracing-outstanding.md) — open decisions and discovered debt
- [Bug: no path info](./bug-no-path-info.md) — investigation when `heard[]` / path hashes are empty ([#385](https://github.com/pskillen/meshflow-api/issues/385))

## Related docs

- [Traceroute feature](../../traceroute/README.md)
- [MeshCore path hash resolution ADR](../../traceroute/adr/0001-mc-path-hash-resolution.md)
- [MeshCore packet ingestion](../../packet-ingestion/meshcore.md)
- [MeshCore packet fields](../../packet-ingestion/MESHCORE_PACKET_FIELDS.md)
