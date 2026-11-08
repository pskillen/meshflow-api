# API Keys

This document describes how Node API keys work in the Meshflow system: the model, typical workflows, packet association, and WebSocket behaviour.

## Model Overview

**NodeAPIKey** is owned by a user and scoped to a constellation. **NodeAuth** links an API key to a ManagedNode:

- A new API key is linked to **one** feeder (ManagedNode) via NodeAuth; see [One Key per Feeder](#one-key-per-feeder). Older keys may still be linked to several (legacy shared keys)
- Each NodeAuth record associates `(api_key, node)` with a unique constraint
- Keys are used for packet ingest and WebSocket commands (e.g. traceroute)

## Who may create API keys

Users in the Django **`feeder`** group (or staff) may create keys for **any** constellation. Trust is placed on the operator, not constellation membership.

Managed-node owners are granted the feeder group via migration when the membership model was removed.

## One Key per Feeder

A key may be linked to **only one active feeder**. Mint one key per feeder.

- A second `add_node` on a key that already has an active link to a different feeder is refused with `400` and
  `{"error": "This API key is already linked to a feeder. Create a separate key for each feeder.", "code": "api_key_already_linked"}`.
- Creating a key with more than one node (across `nodes` and `managed_node_internal_ids`) is refused with the same
  `400` body, and no key is created.
- The Django admin key form refuses a save that adds a node while leaving more than one active link.
- A feeder may still hold two keys during a rotation; the limit is per key, not per feeder.
- Soft-deleted feeders do not count.

**Existing shared keys keep working** on the legacy per-node URLs (`/api/packets/{node_id}/ingest/` and so on). They
can still be renamed, deactivated, deleted or trimmed (remove a node). To replace one, mint one new key per feeder,
roll each feeder over to its own key, then delete the shared key.

`seed_integration_tests` creates its shared key through the ORM directly, so it is not affected by the rule.

### Finding shared keys

```bash
python manage.py report_shared_api_keys
```

Read-only. For each key with more than one active link it prints the key name and id, owner, constellation,
`last_used`, and the linked feeders with their protocols. It ends with two totals: keys shared by more than one
feeder, and keys linked across both protocols.

## Packet Ingest: How Packets Are Associated

Packets are correctly attributed per bot because the **observer** comes from the URL path, not from the API key alone.

1. **Ingest URL includes node ID**

   The bot posts to `/api/packets/{node_id}/ingest/` with its own `my_nodenum` (the Meshtastic device it is connected to).

2. **Permission ties key to node**

   `NodeAuthorizationPermission` checks that the API key is linked to the node in the URL via NodeAuth. If the key is not linked to that node, the request is rejected.

3. **Observer is set from that node**

   The view uses `request.auth.node` (the ManagedNode from the NodeAuth lookup) as the observer.

4. **PacketObservation stores the observer**

   Each packet observation records which ManagedNode reported the packet. The same packet can be observed by multiple ManagedNodes; each gets its own PacketObservation.

**Legacy shared keys (several bots on one existing key):**

- Bot A (device 12345) → `/api/packets/12345/ingest/` → observer = ManagedNode 12345
- Bot B (device 67890) → `/api/packets/67890/ingest/` → observer = ManagedNode 67890

Each bot must use its own `node_id` in the URL. As long as the key is linked to both nodes via NodeAuth, packets are correctly associated per observer.

## WebSocket and Shared Keys (legacy)

New shared links are refused, so this section only applies to existing shared keys.

The WebSocket endpoint (`ws/nodes/?api_key=<key>`) must identify which feeder is connecting when multiple ManagedNodes share one key. Otherwise traceroute and other commands may be delivered to the wrong bot.

| Protocol | Query parameter | Example |
|----------|-----------------|---------|
| Meshtastic | `feeder_node_id` (decimal nodenum) | `feeder_node_id=1127973616` |
| Meshtastic | `feeder_node_id_str` (`!` + 8 hex) | `feeder_node_id_str=!433b82f0` |
| MeshCore | `feeder_pubkey_prefix` (12-hex pubkey prefix) | `feeder_pubkey_prefix=1a37f5aea4a1` |

When only one feeder is linked to the key, no extra query parameter is required.

When multiple feeders share a key and the bot omits the correct disambiguator, the connection is **rejected** (same as MeshCore multi-feeder behaviour).

**Deploy note:** If you run multiple Meshtastic bots on one key, deploy an updated meshtastic-bot that sends `feeder_node_id` on the WebSocket URL before or together with the API change.

Example URLs:

```
ws://{host}/ws/nodes/?api_key={key}&feeder_node_id=1127973616
ws://{host}/ws/nodes/?api_key={key}&feeder_pubkey_prefix=1a37f5aea4a1
```

## Authentication

- **Header**: `X-API-KEY: <key>` or `Authorization: Token <key>`
- **Packet ingest**: Requires `NodeAPIKeyAuthentication` and `NodeAuthorizationPermission`; the key must be linked to the node in the URL path
- **WebSocket**: Validates the key; uses the sole linked feeder, or resolves via `feeder_node_id` / `feeder_node_id_str` (Meshtastic) or `feeder_pubkey_prefix` (MeshCore)

## API Endpoints

- `GET /api/nodes/api-keys/` — List the current user's API keys
- `POST /api/nodes/api-keys/` — Create a new key (requires `name`, `constellation`)
- `PUT /api/nodes/api-keys/{id}/` — Update key (e.g. `name`, `is_active`)
- `DELETE /api/nodes/api-keys/{id}/` — Delete a key
- `POST /api/nodes/api-keys/{id}/add_node/` — Add a ManagedNode to the key (`node_id` in body)
- `POST /api/nodes/api-keys/{id}/remove_node/` — Remove a ManagedNode from the key (`node_id` in body)

Nodes must belong to the same constellation as the API key.
