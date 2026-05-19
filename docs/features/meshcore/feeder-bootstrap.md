# MeshCore feeder bootstrap (Phase 1)

Manual steps to create the first MeshCore feeder so `meshflow-bot` can upload packets.

## Prerequisites

- meshflow-api running with Phase 1 migrations applied (`nodes.0036`, `meshcore_packets.0001`)
- Django admin access
- A **MeshCore** constellation (or create one with `protocol=MeshCore`)

## How the API knows which feeder is uploading

This differs from Meshtastic. You do **not** need an `ObservedNode` row for the feeder, and for MeshCore the API does **not** match the bot’s radio identity to `ManagedNode.node_id`.

| | **Meshtastic** | **MeshCore (Phase 1)** |
| --- | --- | --- |
| **Ingest URL** | `POST /api/packets/{node_id}/ingest/` | `POST /api/meshcore/packets/ingest/` (no `{node_id}` in the path) |
| **What the bot sends** | `node_id` in the URL = device `my_nodenum` (decimal Meshtastic id) | API key header only (`X-API-Key` or `Authorization: Token …`) |
| **How the API picks the observer** | `NodeAuth` must link the key to the `ManagedNode` whose **`node_id`** equals the URL segment | `NodeAuth` must link the key to the **MeshCore** `ManagedNode`; permission loads that row as `request.auth.node` |
| **`ManagedNode.node_id`** | Must match the radio (same number the bot puts in the URL) | Placeholder **`0`** only; **not** used for ingest auth |
| **Payload `from_pubkey` / `from`** | Packet **sender** on the mesh (separate from observer) | Remote node identity in the heard packet; **not** the feeder’s own pubkey |
| **ObservedNode for feeder** | Often exists from node-info traffic; not what authenticates ingest | **Not required** for upload |

**MeshCore bot behaviour:** `meshflow-bot` with `RADIO_PROTOCOL=meshcore` has `my_nodenum = None` and posts to a fixed ingest path. Locally it may know `mc:<12-hex-prefix>` after connect (`MeshCoreRadio.local_node_id`), but Phase 1 **does not** send that on the ingest request. The API never compares the upload to an `ObservedNode` or to `ManagedNode.node_id`.

**What you must configure:** a **`NodeAPIKey`** and exactly **one** **`NodeAuth`** row tying that key to the MeshCore **`ManagedNode`** from step 1. If the key is not linked, ingest returns **403**. If the key is linked to **multiple** nodes, MeshCore ingest can fail (`NodeAuth.objects.get(api_key=…)` expects a single row).

**Shared API keys (known Phase 1 gap):** Meshtastic ingest supports one key linked to many `ManagedNode`s because each bot disambiguates the observer via `{node_id}` in the URL. MeshCore ingest has no URL segment and no feeder pubkey in the body yet, so a shared constellation key cannot identify which feeder uploaded. **Use one API key per MC feeder** until ingest carries feeder identity (e.g. `ManagedNode.mc_pubkey` — see Future below). This is stricter than the Meshtastic shared-key pattern in [`docs/API_KEYS.md`](../../API_KEYS.md).

**Meshtastic pitfall (for comparison):** if `ManagedNode.node_id` in admin does not match the bot’s device id, or `NodeAuth` is missing, `POST /api/packets/{id}/ingest/` is rejected even with a valid API key.

**Future (priority):** **[#295](https://github.com/pskillen/meshflow-api/issues/295)** — feeder identity on ingest so shared constellation API keys work like Meshtastic (`ManagedNode.mc_pubkey` + bot-sent observer id). See also [#279](https://github.com/pskillen/meshflow-api/issues/279).

## 1. Create MC ManagedNode

1. Open **Django admin** → **Managed nodes** → **Add**.
2. Set:
   - **Protocol**: MeshCore
   - **Node ID (placeholder)**: `0` (MeshCore has no Meshtastic numeric id on the wire)
   - **Name**: e.g. `Scottish Mesh MC Feeder`
   - **Owner** / **Constellation**: your MC constellation
   - **Default location** (optional): lat/lon for map display as a feeder pin
3. Save. **Display ID** (read-only after save) is `mc:feeder:<internal id>` — this is not stored in the DB.

**Do not** create feeders via raw SQL on `observednode`: that table still requires `node_id_str` (e.g. `mc:…` from packet ingest). Feeders are `managednode` rows only.

**`node_id_str` on ManagedNode** is a computed property, not a database column. Dropping it from `observednode` is tracked in **[meshflow-api#294](https://github.com/pskillen/meshflow-api/issues/294)** (ADR-0001 §6; deferred in Phase 1).

## 2. Create Node API key + NodeAuth

This step is what binds uploads to the feeder. Without it, the API accepts the key but cannot attach an observer `ManagedNode`.

1. **Node API keys** → **Add** (or reuse an existing key for the constellation).
2. **Node authentications** → **Add**: link the API key to the MC ManagedNode from step 1 (one feeder per key for MeshCore ingest).
3. Put the same key in the bot env as `STORAGE_API_TOKEN` (see step 3).

## 3. Configure meshflow-bot

```bash
RADIO_PROTOCOL=meshcore
MESHCORE_SERIAL_DEVICE=/dev/ttyUSB0   # or MESHCORE_BLE_ADDRESS=...
MESHCORE_UPLOAD_ENABLED=true
STORAGE_API_ROOT=https://your-api.example/api
STORAGE_API_TOKEN=<key from step 2>
STORAGE_API_VERSION=2
```

Restart the bot. Confirm HTTP `POST /api/meshcore/packets/ingest/` in logs (no upload when `MESHCORE_UPLOAD_ENABLED` is false). A **403** usually means the token is wrong, inactive, or not linked via **NodeAuth** to a `protocol=MeshCore` managed node—not a missing `node_id` in the URL.

## 4. Verify in UI

- **MeshCore → Map**: observed nodes appear after ADVERT packets; feeders listed when default location is set.
- **MeshCore → Nodes**: prefix stubs and nodes with/without position.

## Operator trial (24h)

Run one production/staging feeder with upload enabled for 24 hours. Check:

- `MeshCoreRawPacket` / `MeshCorePacketObservation` counts in admin
- `ObservedNode` rows with `protocol=MeshCore`
- UI map and list update with live traffic

No automated gate for the trial; record counts in the deployment notes.
