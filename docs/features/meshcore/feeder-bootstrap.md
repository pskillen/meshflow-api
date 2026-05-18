# MeshCore feeder bootstrap (Phase 1)

Manual steps to create the first MeshCore feeder so `meshflow-bot` can upload packets.

## Prerequisites

- meshflow-api running with Phase 1 migrations applied (`nodes.0036`, `meshcore_packets.0001`)
- Django admin access
- A **MeshCore** constellation (or create one with `protocol=MeshCore`)

## 1. Create MC ManagedNode

1. Open **Django admin** → **Managed nodes** → **Add**.
2. Set:
   - **Protocol**: MeshCore (`2`)
   - **Node id**: `0` (placeholder; MC has no Meshtastic numeric id)
   - **Name**: e.g. `Scottish Mesh MC Feeder`
   - **Owner** / **Constellation**: your MC constellation
   - **Default location** (optional): lat/lon for map display as a feeder pin
3. Save.

## 2. Create Node API key + NodeAuth

1. **Node API keys** → **Add** (or reuse an existing key for the constellation).
2. **Node authentications** → **Add**: link the API key to the MC ManagedNode from step 1.

## 3. Configure meshflow-bot

```bash
RADIO_PROTOCOL=meshcore
MESHCORE_SERIAL_DEVICE=/dev/ttyUSB0   # or MESHCORE_BLE_ADDRESS=...
MESHCORE_UPLOAD_ENABLED=true
STORAGE_API_ROOT=https://your-api.example/api
STORAGE_API_TOKEN=<key from step 2>
STORAGE_API_VERSION=2
```

Restart the bot. Confirm HTTP `POST /api/meshcore/packets/ingest/` in logs (no upload when `MESHCORE_UPLOAD_ENABLED` is false).

## 4. Verify in UI

- **MeshCore → Map**: observed nodes appear after ADVERT packets; feeders listed when default location is set.
- **MeshCore → Nodes**: prefix stubs and nodes with/without position.

## Operator trial (24h)

Run one production/staging feeder with upload enabled for 24 hours. Check:

- `MeshCoreRawPacket` / `MeshCorePacketObservation` counts in admin
- `ObservedNode` rows with `protocol=MeshCore`
- UI map and list update with live traffic

No automated gate for the trial; record counts in the deployment notes.
