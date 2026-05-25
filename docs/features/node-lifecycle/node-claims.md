# Node claims

Node claims let authenticated users prove they control a radio represented by an `ObservedNode`. Proof is always an out-of-band message containing a server-generated **claim key**; the API never trusts UI assertions alone.

## Protocol-specific flows

| Protocol | Proof | Doc |
|----------|--------|-----|
| Meshtastic | Direct message to any Meshtastic feeder | [node-claims-meshtastic.md](node-claims-meshtastic.md) |
| MeshCore | Contact/DM to a MeshCore feeder | [node-claims-meshcore.md](node-claims-meshcore.md) |

## Claim records

`NodeOwnerClaim` represents an attempt to claim a node. A claim row is not ownership by itself.

- `node`: the observed node being claimed.
- `user`: the user attempting the claim.
- `claim_key`: the proof string the radio must send.
- `created_at`: when the claim was started.
- `accepted_at`: when the proof was received (null while pending).

`ObservedNode.claimed_by` is the authoritative owner field once the claim is accepted.

Implementation: [`Meshflow/nodes/claim_authorization.py`](../../../Meshflow/nodes/claim_authorization.py).

## Real-time UI (`node_claim_authorized`)

When proof succeeds, the API emits Django signal **`node_claim_authorized`** (`packets.signals`) with kwargs:

- `node` — the observed node that was claimed
- `claim` — the `NodeOwnerClaim` row (with `accepted_at` set)
- `observer` — the `ManagedNode` feeder that received the proof message

The `ws` app listens and sends **`node_claim_accepted`** JSON to the claiming user’s channel group `user_claims_{user_id}` ([`NodeClaimConsumer`](../../../Meshflow/ws/consumers.py) at `ws/claims/?token=<jwt>`). No other built-in receivers exist today; the signal remains an extension point for notifications or audit.

## Permissions

An authenticated user can start a claim for an unclaimed node. If `ObservedNode.claimed_by` is already set to another user, the API rejects the claim.

Only the claim owner can see or cancel their claim through the claim endpoint.

- The claim owner can delete a pending claim.
- The claim owner can release an accepted claim (`DELETE …/claim/`), clearing `claimed_by` when it matches.
- Django staff do not get a REST shortcut to release another user’s claim.

## Constellation access

Constellations are **public for read** (no membership required). Claiming a node does not create constellation membership rows.

Managed-node setup requires the **feeder** role for API key creation (see [API_KEYS.md](../../API_KEYS.md) and [permissions/README.md](../../permissions/README.md)).

## Observed node retention

Releasing a claim never deletes the `ObservedNode`. If the radio is still active, future packets continue to update it.
