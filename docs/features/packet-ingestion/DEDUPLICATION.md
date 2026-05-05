# Packet Deduplication and Multiple Listeners

This document describes how the Meshflow API handles packet ingestion when multiple listener nodes (meshtastic-bot instances) hear and upload the same packet, and how deduplication works.

## Multiple Listeners Model

- Multiple meshtastic-bot instances run alongside physical Meshtastic radios across the mesh network.
- Each bot is associated with a **ManagedNode** in the system.
- When a packet is transmitted on the mesh, it may be heard by multiple listener nodes.
- Each listener uploads the packet to the API via `POST /api/packets/{node_id}/ingest/`.
- The **observer** (the node that heard the packet) is derived from the API key used for authentication and the `node_id` in the URL path.

## Packet Identity (Meshtastic Spec)

Per the Meshtastic specification:

- **packet_id** is a 32-bit integer assigned by the **sending** node to identify each packet it transmits.
- packet_id is **unique per sender** (each sending node maintains its own sequence).
- **Multiple senders can have identical packet_id values** — there is no global uniqueness.
- There is **no mandate** that packet_id remains unique over long time scales for the same sender. A sender may reuse packet_id after sufficient time (e.g. 10+ minutes).

## Deduplication Rules

The API uses the following logic to determine whether an incoming packet is a duplicate of one already stored:

### Match Key

- **Sender** (`from_int`): The node ID of the packet originator.
- **Packet ID** (`packet_id`): The Meshtastic packet identifier.
- **Time window**: The incoming packet's `rx_time` must fall within a configurable window (default 10 minutes) of the existing packet's `first_reported_time`.

### Duplicate

A packet is treated as a **duplicate** when:

- Same sender (`from_int`)
- Same packet_id
- Incoming `rx_time` is within the deduplication window of the existing packet's `first_reported_time`

In this case: **do not create a new packet**. Instead, create a `PacketObservation` linking the observer to the existing packet (recording that this node heard it).

### New Packet

A packet is treated as a **new packet** when:

- No matching packet exists, or
- A matching packet exists but the incoming `rx_time` is **outside** the deduplication window (e.g. 10+ minutes after `first_reported_time`)

In this case: create a new packet record and an initial `PacketObservation`.

## Logging / Observation Behavior

- **For duplicates**: Do not create a new packet. Create a `PacketObservation` linking the observer to the existing packet. This records that the second (or Nth) listener heard the same packet.
- **For new packets**: Create the packet and an initial `PacketObservation`.
- **Same observer, same packet twice**: If the same observer reports the same packet again (e.g. retry), no new `PacketObservation` is created — the operation is idempotent.

## Data Model

- **RawPacket** (and subclasses: MessagePacket, PositionPacket, NodeInfoPacket, DeviceMetricsPacket, LocalStatsPacket, etc.): One row per unique packet as determined by the deduplication rules.
- **PacketObservation**: Many-to-many relationship between packets and observer nodes. Each observation records which ManagedNode heard the packet, along with rx_time, rx_rssi, rx_snr, hop_limit, hop_start, and channel.

