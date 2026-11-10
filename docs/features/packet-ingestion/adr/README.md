# Architecture Decision Records — packet ingestion

Lightweight ADRs for packet ingestion: 0001–0004 cover MeshCore (MC) ingestion and modelling; 0005–0006 cover Meshtastic (MT) feeder authentication and identity for the 2.8 upgrade. They are **proposed** until merged; reviewer feedback may change individual decisions.

**Tracking:** MC: [meshflow-api#276](https://github.com/pskillen/meshflow-api/issues/276) (epic [meshflow-api#264](https://github.com/pskillen/meshflow-api/issues/264)). MT 2.8: epic [meshflow-api#437](https://github.com/pskillen/meshflow-api/issues/437).

**Evidence:** cite JSON under [`docs/packets/meshcore/`](../../../packets/meshcore/README.md) and field tables in [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md).

## Index

Planned records (add the matching Markdown file in this directory when the ADR is drafted):

| File | Title |
| --- | ----- |
| `0001-mc-node-identity.md` | MeshCore node identity (`ObservedNode`, pubkey / prefix, ADVERT enrichment) |
| `0002-mc-channel-modelling.md` | MeshCore channel modelling (`MessageChannel`, indices, managed node mapping) |
| `0003-mc-broadcast-semantics.md` | Broadcast vs directed semantics (MT vs MC on the wire) |
| `0004-mc-dedup-key.md` | Deduplication key for MC (`pkt_hash`, windows, decoded twins) |
| [`0005-feeder-scoped-auth.md`](0005-feeder-scoped-auth.md) | MT: one API key per feeder, v4 feeder URLs, legacy tracking (accepted) |
| [`0006-meshtastic-identity-linking.md`](0006-meshtastic-identity-linking.md) | MT 2.8: node number = crc32(public key), predicted ids, old/new identity linking (accepted; hardware verified) |

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
