# Architecture Decision Records — MeshCore packet ingestion

Lightweight ADRs for MeshCore (MC) ingestion and modelling, scoped under packet ingestion. They are **proposed** until merged; reviewer feedback may change individual decisions.

**Tracking:** [meshflow-api#276](https://github.com/pskillen/meshflow-api/issues/276) (epic [meshflow-api#264](https://github.com/pskillen/meshflow-api/issues/264)).

**Evidence:** cite JSON under [`docs/packets/meshcore/`](../../../packets/meshcore/README.md) and field tables in [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md).

## Index

Planned records (add the matching Markdown file in this directory when the ADR is drafted):

| File | Title |
| --- | ----- |
| `0001-mc-node-identity.md` | MeshCore node identity (`ObservedNode`, pubkey / prefix, ADVERT enrichment) |
| `0002-mc-channel-modelling.md` | MeshCore channel modelling (`MessageChannel`, indices, managed node mapping) |
| `0003-mc-broadcast-semantics.md` | Broadcast vs directed semantics (MT vs MC on the wire) |
| `0004-mc-dedup-key.md` | Deduplication key for MC (`pkt_hash`, windows, decoded twins) |

## ADR format (use in each `NNNN-title.md`)

Keep each ADR short. Use the following section headings in order:

### Context

What forces the decision: constraints, capture findings, compatibility with Meshtastic (MT) ingestion, open questions.

### Decision

What we will do (or not do), in plain language. Bullet points are fine.

### Consequences

Trade-offs, follow-up work, risks, and what stays out of scope.

### Evidence

Pointers to this repo: e.g. `docs/packets/meshcore/...` sample files and relevant rows in `MESHCORE_PACKET_FIELDS.md`. The full Phase 0.4 capture tree remains in **meshflow-bot** [`docs/meshcore_packets/`](https://github.com/pskillen/meshflow-bot/tree/main/docs/meshcore_packets).
