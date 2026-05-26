# MeshCore feeder bootstrap (Phase 1)

Manual steps to create the first MeshCore feeder so `meshflow-bot` can upload packets.

## Prerequisites

- meshflow-api running with Phase 1 migrations applied (`nodes.0036`, `meshcore_packets.0001`, `nodes.0047` for `mc_pubkey`)
- Django admin access
- A **MeshCore** constellation (or create one with `protocol=MeshCore`)

## How the API knows which feeder is uploading

MeshCore uses the same pattern as Meshtastic: **device identity in the URL**, plus the Node API key.

| | **Meshtastic** | **MeshCore** |
| --- | --- | --- |
| **Ingest URL** | `POST /api/packets/{node_id}/ingest/` | `POST /api/meshcore/feeders/{feeder_pubkey_prefix}/packets/ingest/` |
| **Channel sync** | — | `POST /api/meshcore/feeders/{feeder_pubkey_prefix}/mc-channel-sync/` |
| **Bot version** | `PUT /api/packets/{node_id}/bot-version/` | `PUT /api/meshcore/feeders/{feeder_pubkey_prefix}/bot-version/` |
| **Bot config** | — | `GET /api/meshcore/feeders/{feeder_pubkey_prefix}/bot-config/` (`mc_flood_advert_interval_hours`, default 6h) |
| **What the bot sends** | `node_id` in URL = device nodenum | **12-hex pubkey prefix** in URL (from `mc:` id after connect) |
| **Optional header** | — | `X-MeshCore-Feeder-Pubkey` (64 hex) must match `ManagedNode.mc_pubkey` when set |
| **How the API picks the observer** | `NodeAuth` + URL `node_id` | `NodeAuth` + URL prefix matches `pubkey_to_prefix(mc_pubkey)` |
| **`ManagedNode.meshtastic_node_id`** | Must match the radio | **`NULL`** (not used on the wire) |
| **Payload `from_pubkey`** | Packet sender on the mesh | Remote node in the heard packet; not the feeder |

**Shared constellation API keys:** multiple MeshCore feeders may use the same `NodeAPIKey` if each `ManagedNode` has a distinct **`mc_pubkey`** (full 64-hex from bot logs). The bot disambiguates via the URL prefix, like Meshtastic `{node_id}`.

**403 codes** (JSON `detail` + `code`): `feeder_not_linked`, `feeder_identity_ambiguous`, `feeder_pubkey_mismatch`, `feeder_pubkey_not_configured`.

See [#295](https://github.com/pskillen/meshflow-api/issues/295). Optional follow-up: auto-set `mc_pubkey` on first connect ([#279](https://github.com/pskillen/meshflow-api/issues/279)).

## 1. Create MC ManagedNode

1. Open **Django admin** → **Managed nodes** → **Add** (or use the enrollment wizard when available).
2. Set:
   - **Protocol**: MeshCore
   - **`mc_pubkey`**: full **64-char lowercase hex** from bot connect logs (`SELF_INFO`) — required at save
   - **Name**: e.g. `Scottish Mesh MC Feeder`
   - **Owner** / **Constellation**: your MC constellation
   - **Default location** (optional): lat/lon for map display
3. Save. **Display ID** is `mc:{12-hex-prefix}`.

## 2. API key

1. **Node API keys** → create or reuse a constellation key.
2. **Node authentications** → link the key to this MC ManagedNode, or `POST …/api-keys/{id}/add_node/` with `managed_node_internal_id` (UUID from the managed node row).
3. Multiple feeders may share one key if each has a unique `mc_pubkey`.
4. Put the key in the bot env as `STORAGE_API_TOKEN`.

## 3. Configure meshflow-bot

```bash
RADIO_PROTOCOL=meshcore
MESHCORE_SERIAL_DEVICE=/dev/ttyUSB0   # or MESHCORE_BLE_ADDRESS=...
MESHCORE_UPLOAD_ENABLED=true
STORAGE_API_ROOT=https://your-api.example/api
STORAGE_API_TOKEN=<key from step 2>
STORAGE_API_VERSION=3
```

Restart the bot. Confirm logs show feeder-scoped paths, e.g. `POST /api/meshcore/feeders/{prefix}/packets/ingest/`. Do **not** use `/api/packets/0/bot-version/` for MeshCore.

## 4. Verify in UI

- **MeshCore → Map**: observed nodes after ADVERT packets; feeders with default location appear as pins.
- **MeshCore → Nodes**: prefix stubs and nodes with/without position.

## 5. Channel names (Phase 2.2)

On connect, **meshflow-bot** reads the device channel table and calls **`POST /api/meshcore/feeders/{prefix}/mc-channel-sync/`** so the API mirror matches the radio.

See [text-message-channels.md](./text-message-channels.md).

### Django admin (operators)

- **MeshCore channels** — constellation MC channel catalog only (proxy admin); hashtag rows show with **`#` prefix** in lists.
- **Managed nodes** (MeshCore) — **read-only** “device mirror” table (slot, type, label); **`mc_channels_synced_at`** from last bot sync.
- **Push MC channel config to feeder device** — admin action sends the current mirror to the radio over WebSocket (same mechanism as UI apply). Requires bot connected on **primary** API WS (see dual-API below).

Editing channel definitions in admin does **not** auto-push; use the push action after the mirror reflects what you want on air.

### Dual API upload (`STORAGE_API_2_*`)

If the bot sets **`STORAGE_API_2_ROOT`** + token with `MESHCORE_UPLOAD_ENABLED`, it uploads packets, bot version, and **`mc-channel-sync`** to **both** APIs.

**WebSocket** (apply-to-radio, traceroute) is only started from **`STORAGE_API_ROOT`** (or `MESHFLOW_WS_URL` pointing at the primary). API 2 receives passive mirror updates but will not receive `apply_mc_channel_config` unless WS is also pointed there.

## Operator trial (24h)

Run one production/staging feeder with upload enabled for 24 hours. Check:

- `MeshCoreRawPacket` / `MeshCorePacketObservation` counts in admin
- `ObservedNode` rows with `protocol=MeshCore`
- UI map and list update with live traffic

No automated gate for the trial; record counts in the deployment notes.
