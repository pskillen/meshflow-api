# MeshCore node claims

Node claims let a user prove that they control a MeshCore radio represented by an `ObservedNode` (`protocol=meshcore`, `mc:` / pubkey identity).

## Claim flow

1. The user signs in and opens an unclaimed MeshCore observed node in the UI.
2. The frontend calls `POST /api/nodes/observed-nodes/{internal_id}/claim/` (same endpoint as Meshtastic; lookup accepts `mc:` prefixes and UUIDs).
3. The API returns a `claim_key` (same word+digit format as Meshtastic).
4. From the **physical MeshCore device**, the user sends a **contact/DM** (not a channel/broadcast message) to a MeshCore **feeder** (`ManagedNode` with `protocol=meshcore`). The message body must be **only** the claim key.
5. The feeder bot uploads `contact_text` to `POST /api/meshcore/feeders/{prefix}/packets/ingest/`.
6. [`MeshCoreTextMessageService`](../../../Meshflow/meshcore_packets/services/text_message.py) resolves the sender `ObservedNode` from `from_pubkey` / `from_pubkey_prefix` and calls [`try_accept_node_claim`](../../../Meshflow/nodes/claim_authorization.py).
7. On match, `claimed_by` is set, `accepted_at` is recorded, `node_claim_authorized` fires, and the UI receives **`node_claim_accepted`** on `ws/claims/`.

Channel (`CHANNEL_TEXT`) messages are **not** accepted for claims (same security model as ignoring Meshtastic broadcasts).

## Identity notes

- Start the claim against the same observed-node row the feeder will attribute to the DM (usually `mc:{12-hex-prefix}` until a full `mc_pubkey` is known).
- Prefix-only nodes are valid; the DM’s `from_pubkey_prefix` must match the claimed node.

## Operator steps (bot)

See [meshflow-bot `docs/MESHCORE.md`](https://github.com/pskillen/meshflow-bot/blob/main/docs/MESHCORE.md) — “Claiming a node”.

## Shared concepts

See [node-claims.md](node-claims.md) for `NodeOwnerClaim` fields, permissions, and signals.
