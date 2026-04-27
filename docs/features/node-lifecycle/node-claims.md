# Node Claims

Node claims let a user prove that they control a Meshtastic radio represented by an `ObservedNode`.

## Claim Flow

1. The user signs in to the frontend.
2. The user finds an unclaimed observed node.
3. The frontend calls `POST /api/nodes/observed-nodes/{node_id}/claim/`.
4. The API creates a `NodeOwnerClaim` with a generated `claim_key`.
5. The user sends the claim key as a direct Meshtastic message from their node to a Meshflow managed node.
6. Packet ingestion receives that text message.
7. `Meshflow/packets/services/text_message.py` matches the message body to the claim key.
8. The API sets `ObservedNode.claimed_by` to the claiming user and marks `NodeOwnerClaim.accepted_at`.

Accepted claims do not create the observed node. The observed node must already exist, usually because it was discovered from packet ingestion.

## Claim Records

`NodeOwnerClaim` represents an attempt to claim a node. A claim row is not ownership by itself.

- `node`: the observed node being claimed.
- `user`: the user attempting the claim.
- `claim_key`: the proof string the radio must send.
- `created_at`: when the claim was started.
- `accepted_at`: when the proof was received.

`ObservedNode.claimed_by` is the authoritative owner field once the claim is accepted.

## Permissions

An authenticated user can start a claim for an unclaimed node. If `ObservedNode.claimed_by` is already set to another user, the API must reject the claim.

Only the user who owns a claim can see or cancel that claim through the claim endpoint.

When claim removal is implemented:

- The claim owner can delete their own pending claim.
- The claim owner can release their own accepted claim.
- Releasing an accepted claim clears `ObservedNode.claimed_by` when it points at the current user.
- Django staff do not get a REST endpoint to release another user's valid claim.
- If an administrator needs to correct ownership, they can use Django Admin or a future purpose-built admin flow.

## Constellation Membership

When a user claims a node, they are added to the relevant constellation as a viewer. Viewer membership is enough to observe constellation data, but it is not currently enough to complete managed-node setup. The UI still lets the user try to convert the node to managed, which fails later during API-key setup.

That onboarding bug is tracked separately in meshtastic-bot-ui issue #205.

## Observed Node Retention

Releasing a claim never deletes the `ObservedNode`. If the radio is still active, future packets continue to update it. If it is no longer active, it naturally falls out of recent-node views according to the same time-window behavior as any other observed node.
