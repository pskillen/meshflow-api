# API Keys

This document describes how Node API keys work in the Meshflow system: the model, typical workflows, packet association, and WebSocket behaviour.

## Model Overview

**NodeAPIKey** is owned by a user and scoped to a constellation. **NodeAuth** links an API key to one or more ManagedNodes:

- One API key can be linked to **multiple** ManagedNodes via NodeAuth
- Each NodeAuth record associates `(api_key, node)` with a unique constraint
- Keys are used for packet ingest and WebSocket commands (e.g. traceroute)

## Who may create API keys

Users in the Django **`feeder`** group (or staff) may create keys for **any** constellation. Trust is placed on the operator, not constellation membership.

Managed-node owners are granted the feeder group via migration when the membership model was removed.

## One Key per Node vs One per User

Both patterns are supported:

- **One key per node**: Create a key and assign it to a single ManagedNode. This is the typical workflow when setting up a new managed node.
- **One key per user**: Create a key and assign it to multiple ManagedNodes. Useful if one user runs several bots and wants to manage a single key.

The integration test seed (`seed_integration_tests`) creates one API key linked to two ManagedNodes, demonstrating shared-key support.

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

**When multiple bots share one API key:**

- Bot A (device 12345) → `/api/packets/12345/ingest/` → observer = ManagedNode 12345
- Bot B (device 67890) → `/api/packets/67890/ingest/` → observer = ManagedNode 67890

Each bot must use its own `node_id` in the URL. As long as the key is linked to both nodes via NodeAuth, packets are correctly associated per observer.

## WebSocket and Shared Keys

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
