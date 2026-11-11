# Meshtastic node claims

Node claims let a user prove that they control a Meshtastic radio represented by an `ObservedNode` (`protocol=meshtastic`).

## Claim flow

1. The user signs in to the frontend.
2. The user finds an unclaimed observed node.
3. The frontend calls `POST /api/nodes/observed-nodes/{internal_id}/claim/`.
4. The API creates a `NodeOwnerClaim` with a generated `claim_key`.
5. The user sends the claim key as a **direct Meshtastic message** (not broadcast) from their node to a Meshflow managed (feeder) node.
6. Packet ingestion receives that text message.
7. [`Meshflow/packets/services/text_message.py`](../../../Meshflow/packets/services/text_message.py) calls [`try_accept_node_claim`](../../../Meshflow/nodes/claim_authorization.py).
8. The API sets `ObservedNode.claimed_by` and `NodeOwnerClaim.accepted_at`, emits `node_claim_authorized`, and pushes **`node_claim_accepted`** to the claimant over `ws/claims/`.

The claim page uses the WebSocket event for near-real-time success; it falls back to slow HTTP polling if the socket is unavailable.

Accepted claims do not create the observed node. The observed node must already exist, usually from packet ingestion.

## Claiming your node's new number

On 2.8 a radio that gets a new key shows up under a new number, as a new `ObservedNode`, and an identity link records
that the two rows are the same radio (see [identity links](../packet-ingestion/meshtastic.md)). If you own the old row,
you can claim the new one without sending a claim key: `POST /api/nodes/observed-nodes/{id}/claim-from-previous/` on the
**new** node.

- It needs a live link from a row you own to this node, with this node unclaimed. The link must be strong: `public_key`
  or `feeder_rekey` evidence, or `confirmed` by staff or an owner. A `predicted_number` or `mac` link that is only
  `auto` is `evidence_too_weak` (409).
- It sets `claimed_by`, stores an already accepted `NodeOwnerClaim` and pushes `node_claim_accepted`, like a claim
  accepted by message. Your old claim is untouched.
- Errors are `{code, detail}`: `no_previous` (404), `not_owner` (403), `already_claimed` (409), `evidence_too_weak` (409).
  Repeating the call for a node you already hold is a 200.
- Undo is the ordinary claim `DELETE`.

## Shared concepts

See [node-claims.md](node-claims.md) for `NodeOwnerClaim` fields, permissions, constellation access, retention, and the `node_claim_authorized` signal.
