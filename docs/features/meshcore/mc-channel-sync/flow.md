# mc-channel-sync — flow and API

Purpose: how a device channel table becomes API state, and how operator edits return to the radio.

---

## 1. Device → API (`mc-channel-sync`)

### Trigger

| When | Who calls |
|------|-----------|
| Bot connects to companion (after `SELF_INFO`) | `meshflow-bot` — `sync_channels_to_storage_apis_async` |
| After WebSocket `apply_mc_channel_config` succeeds | Bot re-syncs to **all** configured storage APIs |
| Django admin **Push MC channel config** | Same as apply (mirror payload), then bot re-syncs |

The bot does **not** pull channel config from the API on startup.

### Bot read path

1. Wait `CHANNEL_READ_DELAY_S` (2 s) after connect so the channel table is stable.
2. For each index `0 .. max_channels-1` (default 16), `meshcore.commands.get_channel(idx)`.
3. Map `CHANNEL_INFO` to snapshot rows in [`channels.py`](https://github.com/pskillen/meshflow-bot/blob/main/src/meshcore/channels.py):
   - Name starting with `#` → `mc_channel_type: HASHTAG`, `mc_hashtag` set (no `#` in value)
   - Otherwise → `PUBLIC`, `mc_hashtag: null`
4. Build body: `{ "channels": [...], "synced_at": "<ISO8601 UTC>" }`.
5. `POST` to each `StorageAPIWrapper` in `storage_apis` (primary + optional secondary).

Empty named slots are omitted from the snapshot. If no channels are found, the bot logs a per-slot scan warning.

### HTTP

| | |
|--|--|
| **Method / path** | `POST /api/meshcore/feeders/{feeder_pubkey_prefix}/mc-channel-sync/` |
| **Auth** | `NodeAPIKeyAuthentication` + `MeshCoreFeederPermission` |
| **Feeder resolution** | URL **12-hex prefix** must match `pubkey_to_prefix(ManagedNode.mc_pubkey)`; optional `X-MeshCore-Feeder-Pubkey` (64 hex) must match when `mc_pubkey` is set |

See [feeder-bootstrap.md](../feeder-bootstrap.md) for 403 codes (`feeder_not_linked`, `feeder_pubkey_mismatch`, etc.).

**Request body** (`McChannelSyncSerializer`):

| Field | Required | Description |
|-------|----------|-------------|
| `channels` | Yes | Array of snapshot entries |
| `synced_at` | No | Client timestamp; defaults to server now |

**Each channel entry:**

| Field | Required | Description |
|-------|----------|-------------|
| `mc_channel_idx` | Yes | Device slot, 0–63 |
| `name` | Yes | Channel name (hashtag channels: tag without leading `#` in stored canonical `name` where applicable) |
| `mc_channel_type` | Yes | `PUBLIC` or `HASHTAG` (plain strings, not gettext) |
| `mc_hashtag` | No | Normalized hashtag when `HASHTAG`; omitted or null for `PUBLIC` |

Example:

```json
{
  "channels": [
    { "mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC", "mc_hashtag": null },
    { "mc_channel_idx": 1, "name": "galloway", "mc_channel_type": "HASHTAG", "mc_hashtag": "galloway" }
  ],
  "synced_at": "2026-05-20T12:00:00Z"
}
```

**Response** (`200`):

| Field | Description |
|-------|-------------|
| `status` | `"success"` |
| `synced_at` | `ManagedNode.mc_channels_synced_at` after reconcile |
| `mc_channels` | Feeder mirror: canonical fields + `mc_channel_idx` per link |

**Errors:** `400` validation or `mc_channel_idx` out of range; `403` feeder auth.

### API reconcile (`reconcile_mc_channels`)

Transactional steps ([`channel_sync.py`](../../../Meshflow/meshcore_packets/services/channel_sync.py)):

1. For each snapshot entry: `upsert_canonical_mc_channel(constellation, entry)` → `MessageChannel`.
2. `ManagedNodeMcChannelLink.update_or_create(managed_node, mc_channel_idx, message_channel=canonical)`.
3. Delete any link rows for this feeder whose `mc_channel_idx` was **not** in the snapshot.
4. Set `managed_node.mc_channels_synced_at` from `synced_at` or now.

An **empty** `channels` array clears all feeder links (catalog rows may remain for other feeders or history).

---

## 2. UI / admin → device (`apply-mc-channel-config`)

### Trigger

| When | Who |
|------|-----|
| Node Settings **Apply to radio** | Owner JWT |
| Django admin **Push MC channel config to feeder device** | Staff; uses current mirror via `build_apply_channels_for_managed_node` |

### HTTP

| | |
|--|--|
| **Method / path** | `POST /api/meshcore/managed-nodes/{internal_id}/apply-mc-channel-config/` |
| **Auth** | `IsAuthenticated`; managed node must belong to `request.user` |
| **Body** | `McChannelApplySerializer`: `{ "channels": [ ... ] }` — same entry shape as sync (may omit `mc_channel_idx` on entries that only update catalog intent; mirror apply includes indices) |

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | `apply_mc_channel_config` dispatched to bot group |
| `404` | Unknown or non-owned managed node |
| `503` `feeder_bot_not_connected` | No bot WebSocket on `node_mc_{internal_id}` Redis group |
| `503` `command_dispatch_unavailable` | Channel layer / Redis unavailable |

### WebSocket command

Dispatched via Django Channels (`dispatch_node_command`) to group `node_mc_{managed_node.internal_id}`:

```json
{
  "type": "apply_mc_channel_config",
  "channels": [ { "mc_channel_idx": 0, "name": "...", "mc_channel_type": "PUBLIC", "mc_hashtag": null } ]
}
```

**meshflow-bot** (`MeshflowBot` handler):

1. `apply_device_channels` — `set_channel(idx, name)` per row; hashtag names written with `#` prefix on device.
2. Re-run channel sync to all `storage_apis`.

Bot WebSocket connects when `STORAGE_API_ROOT` + token are set; URL is derived from API base unless `MESHFLOW_WS_URL` is set. Feeder **12-hex prefix** is appended on connect.

### Horizontal scaling

Apply uses **Redis DB 0** channel layer ([`docs/REDIS.md`](../../../REDIS.md)), not in-process signals. Any API worker can `group_send`; the bot must share that Redis and register on the feeder group. Details: [operations.md](operations.md).

---

## 3. Ingest coupling (read-only here)

When `channel_text` arrives before the first sync, [`resolve_mc_channel`](../../../Meshflow/meshcore_packets/services/channel.py):

1. Clamps `channel_idx` to 0–63.
2. Looks up `ManagedNodeMcChannelLink` for `(observer, channel_idx)`.
3. If missing: creates placeholder canonical `MessageChannel` (`MC channel N`) + link.

The next **mc-channel-sync** overwrites placeholder metadata from the device. Multiple feeders with the same logical hashtag at **different** indices share one canonical row after sync ([ADR-0002](../../packet-ingestion/adr/0002-mc-channel-modelling.md)).

Text dedup keys include `message_channel_id`, so canonical identity must be stable across feeders.

---

## Related

- [data-model.md](data-model.md) — fields and uniqueness
- [operations.md](operations.md) — dual API, local dev 503s
- [text-message-channels.md](../text-message-channels.md) — wire format and `TextMessage` pipeline
