# Node Lifecycle

This feature area describes how Meshtastic radio nodes move through Meshflow:

1. An observed node is discovered from ingested packets.
2. A user proves ownership by claiming the observed node.
3. The owner can convert that node into a managed node so it can feed packets into Meshflow.
4. The owner can later release the claim or remove the managed-node role without deleting the observed node.

Observed nodes are not manually created by users during normal operation. They are discovered when a managed node ingests packets and the packet source is not already known. Packet ingestion creates the `ObservedNode`, keeps `last_heard` current, and updates related latest-status data such as position and metrics.

On **first** creation of an `ObservedNode`, the API may queue one **new-node baseline** traceroute (trigger type 6) using the same durable `AutoTraceRoute` dispatch queue as scheduled and mesh-monitoring traceroutes. This captures an early route snapshot for topology evidence; it is separate from DX Monitoring event detection (see [Traceroute](../traceroute/README.md)).

## Lifecycle Documents

- [Node claims](node-claims.md): how users prove ownership of an observed node.
- [Managed nodes](managed-nodes.md): how claimed nodes become feeder nodes.
- [Removal](removal.md): how ownership and managed-node status are removed.

## Core Models

- `ObservedNode`: a Meshtastic radio node seen on the mesh.
- `NodeLatestStatus`: denormalized latest position and metrics for an observed node.
- `NodeOwnerClaim`: a pending or accepted ownership proof for an observed node.
- `ManagedNode`: a Meshflow feeder node operated by a user.
- `NodeAPIKey` and `NodeAuth`: API-key credentials and managed-node associations for bot ingestion.

## Discovery

The primary discovery path is packet ingestion. Any packet type can create an `ObservedNode` if the packet source does not already exist.

- Main service path: `Meshflow/packets/services/base.py`
- Creation helper: `_get_or_create_from_node()`
- Signal emitted for new nodes: `new_node_observed`

When the first packet is not a NodeInfo packet, the node is created with placeholder names. Later NodeInfo packets can update user name, hardware model, role, public key, MAC address, and related fields.

`NodeUpsertView` is a secondary API path used by authenticated nodes to update their own observed-node details. It is not the normal user-facing discovery flow.

## Permission Summary

- Unclaimed observed nodes can be claimed by authenticated users who can complete the claim-key proof.
- Accepted claims set `ObservedNode.claimed_by` to the claiming user.
- Claim owners can release their own claim. Staff/admin users do not get a REST shortcut to release someone else's claim.
- Managed nodes can be removed by the managed-node owner or by Django staff.
- Constellation admins are not treated as system admins for managed-node removal.
- Removing managed-node status does not remove the observed-node claim.

The feeder onboarding permission bug where claimants are added to a constellation as viewers, which is not enough to complete managed-node setup, is tracked separately in meshtastic-bot-ui issue #205.
