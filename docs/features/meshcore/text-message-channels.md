# MeshCore text messages and channels

How MeshCore **group text** and **channel configuration** flow from the radio through **meshflow-bot**, **meshflow-api**, and **meshflow-ui**. This document is the feature-level guide for Phase 2 work under epic [#266](https://github.com/pskillen/meshflow-api/issues/266).

**Tracking issues:**

| Issue | Repo | Focus |
|-------|------|--------|
| [#296](https://github.com/pskillen/meshflow-api/issues/296) | meshflow-api | Ingest MC text → `TextMessage` business model + history API |
| [#297](https://github.com/pskillen/meshflow-api/issues/297) | meshflow-api (+ ui, bot children) | Configure MC channels on feeders; sync to device |

**Normative ADRs:** [ADR-0002](../packet-ingestion/adr/0002-mc-channel-modelling.md) (channels), [ADR-0003](../packet-ingestion/adr/0003-mc-broadcast-semantics.md) (broadcast vs DM), [ADR-0001](../packet-ingestion/adr/0001-mc-node-identity.md) (sender identity on text).

**Related:** [feeder-bootstrap.md](feeder-bootstrap.md), [README.md](README.md) (phase docs), [MESHCORE_PACKET_FIELDS.md](../packet-ingestion/MESHCORE_PACKET_FIELDS.md).

---

## Mental model: Meshtastic vs MeshCore

| | **Meshtastic** | **MeshCore** |
|---|----------------|--------------|
| Channel on radio | Fixed slots 0–7, PSK + name in firmware | Arbitrary list on companion; **index** on wire, **name** only in device config |
| Feeder channel config in API | Eight FKs: `ManagedNode.meshtastic_channel_0..7` → `MessageChannel` | **Planned:** `ManagedNode.mc_channels` M2M → `MessageChannel` rows |
| What a text packet carries | Channel index + sender node id | `channel_message`: **index + body only** (no sender pubkey); `contact_message`: **12-hex sender prefix** + body |
| Broadcast vs DM | `to_int == 0xFFFFFFFF` vs directed node id | Broadcast = **no** `to_pubkey*` on wire; channel text is always broadcast on that index ([ADR-0003](../packet-ingestion/adr/0003-mc-broadcast-semantics.md)) |
| UI today | Slot 0–7 mapping on [Node Settings](https://github.com/pskillen/meshflow-ui/blob/main/src/pages/user/NodeSettings.tsx) | **Planned:** add/remove public and hashtag channels per MC feeder |

MeshCore channels are still **scoped to a constellation**: channel index `0` in one region is not the same `MessageChannel` row as index `0` in another ([ADR-0002](../packet-ingestion/adr/0002-mc-channel-modelling.md) §6).

---

## End-to-end architecture

### Ingest path (implemented today)

Text heard on the mesh is uploaded as raw packets first; normalisation into `TextMessage` is **planned** ([#296](https://github.com/pskillen/meshflow-api/issues/296)).

```mermaid
sequenceDiagram
  participant Radio as MeshCore_radio
  participant Bot as meshflow_bot
  participant API as meshflow_api_ingest
  participant Raw as MeshCoreTextPacket
  participant TM as TextMessage

  Radio->>Bot: channel_message or contact_message
  Bot->>Bot: translate + MeshCorePacketSerializer
  Bot->>API: POST /api/meshcore/packets/ingest/
  API->>Raw: save + MeshCorePacketObservation
  API->>API: meshcore_text_packet_received
  Note over TM: Subscriber planned #296
  API-->>TM: create TextMessage row
```

### Configuration path (planned #297)

Operator-defined channels on the feeder are the **source of truth** in the API; the bot pushes them to the device and reconciles on connect.

```mermaid
sequenceDiagram
  participant UI as meshflow_ui
  participant API as meshflow_api
  participant WS as bot_WebSocket
  participant Bot as meshflow_bot
  participant Radio as MeshCore_radio

  UI->>API: CRUD mc_channels on ManagedNode
  API->>WS: apply_mc_channel_config
  WS->>Bot: command
  Bot->>Radio: meshcore channel read/write
  Bot->>API: optional sync ack / index report
  Note over Bot,API: On connect: GET config, reconcile device vs DB
```

Today the bot **does not** start the WebSocket client for `RADIO_PROTOCOL=meshcore` (Meshtastic-only). Enabling WS for MC feeders is part of [#297](https://github.com/pskillen/meshflow-api/issues/297).

---

## On the wire (what the bot sees)

From Phase 0.4 captures ([meshflow-bot `docs/meshcore_packets/`](https://github.com/pskillen/meshflow-bot/tree/main/docs/meshcore_packets)):

### `channel_message` → group / channel text

Decoded payload includes:

- `channel_idx` — zero-based integer (dispatch key on the wire)
- `text` — message body
- `sender_timestamp`, `path_len`, `path_hash_mode`, etc.

It does **not** include channel name, hashtag string, sender full pubkey, or destination fields. Meshflow cannot learn “Galloway” or “#foo” from the packet alone.

### `contact_message` → DM / private text

- `pubkey_prefix` — 12 hex chars (6-byte sender prefix)
- `text`, `channel_idx` (often `0` in samples; DMs are not a channel in the ADR sense)

See [MESHCORE_PACKET_FIELDS.md](../packet-ingestion/MESHCORE_PACKET_FIELDS.md) for field tables.

---

## meshflow-bot

### Environment (feeder)

See [feeder-bootstrap.md](feeder-bootstrap.md) and [meshflow-bot `docs/MESHCORE.md`](https://github.com/pskillen/meshflow-bot/blob/main/docs/MESHCORE.md).

| Variable | Role |
|----------|------|
| `RADIO_PROTOCOL=meshcore` | Use `MeshCoreRadio` + `MeshCorePacketSerializer` |
| `MESHCORE_UPLOAD_ENABLED=true` | POST packets to API (otherwise capture-only dumps) |
| `STORAGE_API_ROOT` / `STORAGE_API_TOKEN` | `POST /api/meshcore/packets/ingest/` with Node API key |
| `MESHCORE_SERIAL_DEVICE` or `MESHCORE_BLE_ADDRESS` | Transport to companion |

Uploadable text events today ([`MeshCorePacketSerializer`](https://github.com/pskillen/meshflow-bot/blob/main/src/meshcore/serializers.py)):

| Bot `event_type` | `payload_type` sent to API | Notes |
|------------------|----------------------------|--------|
| `channel_message` | `channel_text` | No `from_pubkey`; `channel_idx` + `text` |
| `contact_message` | `contact_text` | `from_pubkey_prefix` + `text` |
| `rx_log_data` + `ADVERT` | `advert` | Position/name; **not** channel text (separate pipeline) |

Non-text `rx_log_data` (e.g. `TEXT_MSG`, `PATH`) is skipped via `MeshCoreSkipUpload`.

### Translation and upload shape

1. [`event_to_incoming_packet`](https://github.com/pskillen/meshflow-bot/blob/main/src/meshcore/translation.py) builds a generic `IncomingPacket` with `raw` envelope `{ meshcore, type, payload, attributes }`.
2. [`MeshCorePacketSerializer.serialise_raw_packet`](https://github.com/pskillen/meshflow-bot/blob/main/src/meshcore/serializers.py) maps to API ingest JSON, including top-level `channel_idx` and `text` for text types.

Example ingest body (channel text, illustrative):

```json
{
  "event_type": "channel_message",
  "payload_type": "channel_text",
  "channel_idx": 0,
  "text": "hello mesh",
  "pkt_hash": 123456,
  "rx_time": 1730000000,
  "rx_rssi": -90,
  "raw": { "meshcore": true, "type": "channel_message", "payload": { "...": "..." } }
}
```

### Bot channel configuration (planned #297)

**Not implemented yet.** Intended behaviour:

1. **On connect** — `GET` the feeder’s `mc_channels` from the API; read the device’s channel table via `meshcore` APIs; reconcile (add missing channels on radio, report indices).
2. **On UI save** — receive WebSocket command `apply_mc_channel_config` with the desired channel list (public vs hashtag, name, optional hashtag string); write to radio; ack success/failure.
3. **Channel types (v1)** — **public** and **hashtag** only, matching companion capabilities under discussion in [#297](https://github.com/pskillen/meshflow-api/issues/297).

The bot remains responsible for **upload only** in Phase 1; configuration is an additional responsibility in Phase 2.

---

## meshflow-api — data models

### `MessageChannel` (constellation-scoped)

[`Meshflow/constellations/models.py`](../../../Meshflow/constellations/models.py)

| Field | Today | Planned (#297) |
|-------|--------|----------------|
| `name` | Operator-facing label | Same; set in UI, not from wire |
| `constellation` | FK | Unchanged |
| `protocol` | `MESHTASTIC` or `MESHCORE` | Unchanged |
| `mc_channel_idx` | Nullable; set on MC ingest | Unique per `(constellation, protocol)` for MC |
| `mc_channel_type` | — | `PUBLIC` / `HASHTAG` |
| `mc_hashtag` | — | Hashtag string when type is `HASHTAG` |

Meshtastic channels use PSK-backed slots on the managed node (`meshtastic_channel_0..7`). MeshCore does **not** use those slots.

### `ManagedNode` (feeder)

| Field | Today | Planned (#297) |
|-------|--------|----------------|
| `protocol` | `MESHCORE` for MC feeders | Unchanged |
| `meshtastic_channel_0..7` | MT only | Unchanged for MT |
| `mc_channels` | — | M2M to `MessageChannel` (`protocol=MESHCORE`) |

Authentication: one Node API key per MC feeder via `NodeAuth` → `ManagedNode` ([feeder-bootstrap.md](feeder-bootstrap.md)). Ingest has no `{node_id}` in the URL; the observer is whichever node owns the key.

### Raw ingest: `MeshCoreTextPacket`

[`Meshflow/meshcore_packets/models.py`](../../../Meshflow/meshcore_packets/models.py)

| Field | Purpose |
|-------|---------|
| `text` | Message body |
| `channel` | FK → `MessageChannel` resolved at ingest |
| `from_pubkey` / `from_pubkey_prefix` | Sender when known (contact); empty for channel text |
| `to_pubkey_prefix` | DM directed-to-us semantics (often null in bot upload today) |

Parent `MeshCoreRawPacket` holds `event_type`, `pkt_hash`, `rx_time`, `observer`, etc.

### Observations: `MeshCorePacketObservation`

Per-feeder sighting of a packet, with optional `channel` FK (same `MessageChannel` as on the text row when applicable).

### `TextMessage` (business model)

[`Meshflow/text_messages/models.py`](../../../Meshflow/text_messages/models.py) — **Meshtastic-only today.**

| Field | Today | Planned (#296) |
|-------|--------|------------------|
| `original_packet` | FK → MT `MessagePacket` | Still for MT |
| `original_mc_packet` | — | FK → `MeshCoreTextPacket` |
| `protocol` | — | `MESHTASTIC` / `MESHCORE` on every row |
| `sender` | Required FK → `ObservedNode` | **Nullable** for channel text (no sender on wire) |
| `channel` | FK → `MessageChannel` | From packet / observation |
| `recipient_meshtastic_node_id` | MT broadcast sentinel | Null for MC broadcast |
| `sent_at` | `auto_now_add` | MC: use packet `rx_time` |

**Dedup:** one `TextMessage` per raw packet (`original_packet` or `original_mc_packet`).

**History API (planned):** existing `GET /api/messages/` list stays **channel broadcast** only (like MT today): include MC rows with `protocol=MESHCORE`, `sender` null, channel set; **store** contact/DM rows but expose them via a future DM endpoint.

---

## meshflow-api — ingest and channel resolution

**Endpoint:** `POST /api/meshcore/packets/ingest/`  
**Code:** [`MeshCorePacketIngestSerializer`](../../../Meshflow/meshcore_packets/serializers.py), [`MeshCorePacketIngestView`](../../../Meshflow/meshcore_packets/views.py)

Flow for text packets:

1. Validate envelope (`payload_type` `channel_text` or `contact_text`, `text` required).
2. Dedup by `pkt_hash` + time window ([`dedup.py`](../../../Meshflow/meshcore_packets/services/dedup.py)).
3. **`resolve_mc_channel(observer, channel_idx)`** — [`channel.py`](../../../Meshflow/meshcore_packets/services/channel.py).

### `resolve_mc_channel` — today vs planned

**Today:** `get_or_create` `MessageChannel` on `(constellation, protocol=MESHCORE, mc_channel_idx)` with default name `"MC channel {idx}"`. Does **not** yet attach the row to `ManagedNode.mc_channels`.

**Planned (ADR-0002 + #297):**

1. Reject or clamp `channel_idx` to `0..63`.
2. Prefer `observer.mc_channels.filter(mc_channel_idx=idx).first()`.
3. If missing, auto-create placeholder channel, attach to `observer.mc_channels`, allow UI rename/type later.

This links **heard** traffic to **operator-configured** channels without requiring names on the wire.

### Signals

| Signal | When | Subscriber |
|--------|------|------------|
| `meshcore_packet_received` | Every stored packet | Identity upsert ([`receivers.py`](../../../Meshflow/meshcore_packets/receivers.py)) |
| `meshcore_text_packet_received` | `MeshCoreTextPacket` saved | **Planned:** `text_messages` → `TextMessage` ([#296](https://github.com/pskillen/meshflow-api/issues/296)) |

Identity receiver **skips** channel text (no `from_pubkey` / prefix). Contact text creates or touches a **prefix stub** `ObservedNode` per [ADR-0001](../packet-ingestion/adr/0001-mc-node-identity.md).

---

## meshflow-api — channel CRUD and WebSocket (planned #297)

**REST (illustrative paths):**

- List/replace MC channels on a managed node the user owns.
- Create channel: `{ name, mc_channel_type, mc_hashtag?, mc_channel_idx }` — index may come from UI or from post-sync device report.
- Delete: remove from `mc_channels` M2M.

**Permissions:** node owner or constellation editor (same spirit as managed-node edits).

**WebSocket:** new command type e.g. `apply_mc_channel_config` to the connected MC feeder (pattern: remote Meshtastic traceroute on [`/ws/nodes/`](../../../Meshflow/ws/tests/test_node_consumer.py)). Optional ack events for UI feedback.

**OpenAPI:** extend `ManagedNode`, `MessageChannel`, and WS command schemas when implemented.

---

## meshflow-ui

### Today

- **Meshtastic feeders:** [Node Settings](https://github.com/pskillen/meshflow-ui/blob/main/src/pages/user/NodeSettings.tsx) maps **slots 0–7** to constellation `MessageChannel` rows via `meshtastic_channel_*` PATCH fields.
- **MeshCore feeders:** no channel editor; MC map/nodes views do not configure channels.

### Planned (#297)

When `ManagedNode.protocol === MESHCORE`:

- Channel **list** UI (not eight slots): add/remove channels.
- Fields: display name, type (**Public** / **Hashtag**), hashtag value when applicable, `mc_channel_idx` (from API or after sync).
- Calls new meshflow-api endpoints; shows errors if bot offline or WS apply fails.

**Message history UI** for MC protocol filter is **out of scope** for #297 (separate epic/UI work); #296 only requires API list support for channel broadcast messages.

---

## Operator checklist

1. Create MC **constellation** and **ManagedNode** feeder ([feeder-bootstrap.md](feeder-bootstrap.md)).
2. Link **Node API key** via `NodeAuth` (one key per feeder recommended).
3. Configure bot env (`MESHCORE_UPLOAD_ENABLED`, storage API).
4. **(Planned #297)** In UI, define public/hashtag channels on the feeder; wait for bot sync to device.
5. Confirm `channel_message` ingest: `MeshCoreTextPacket` rows with `channel` FK and matching `mc_channel_idx`.
6. **(Planned #296)** Confirm `TextMessage` rows appear on `GET /api/messages/?protocol=2` (or mixed list) for channel traffic.

---

## Implementation status summary

| Capability | Status |
|------------|--------|
| Bot upload `channel_text` / `contact_text` | **Done** (Phase 1) |
| API store `MeshCoreTextPacket` + observation | **Done** |
| `resolve_mc_channel` placeholder `MessageChannel` | **Done** (partial ADR-0002) |
| `ManagedNode.mc_channels` + channel types | **Planned** [#297](https://github.com/pskillen/meshflow-api/issues/297) |
| Bot device channel sync + WS apply | **Planned** [#297](https://github.com/pskillen/meshflow-bot/issues/297) (child) |
| UI MC channel settings | **Planned** [#297](https://github.com/pskillen/meshflow-ui/issues/297) (child) |
| `TextMessage` + `protocol` field | **Planned** [#296](https://github.com/pskillen/meshflow-api/issues/296) |
| MC message history in UI | **Deferred** (epic #266 UI) |

---

## References

- [ADR-0002 — MC channel modelling](../packet-ingestion/adr/0002-mc-channel-modelling.md)
- [ADR-0003 — MC broadcast semantics](../packet-ingestion/adr/0003-mc-broadcast-semantics.md)
- [ADR-0001 — MC node identity](../packet-ingestion/adr/0001-mc-node-identity.md)
- [Packet ingestion — MeshCore section](../packet-ingestion/README.md)
- [Implementation plan — Phase 2.1+](implementation-plan.md)
- [API keys & WebSocket](../../API_KEYS.md)
