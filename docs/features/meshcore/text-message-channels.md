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
| Feeder channel config | API slot FKs → `MessageChannel` (operator maps slots in UI) | **Planned:** device is source of truth; API **mirror** via bot `mc-channel-sync` on connect |
| Feeder channel link in API | `meshtastic_channel_0..7` | `ManagedNode.mc_channels` M2M (reconciled from device snapshot) |
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

The **MeshCore device / companion** is the **source of truth** for channel names, types (public / hashtag), and indices. The API holds a **mirror** per feeder (`ManagedNode.mc_channels`). On every bot connect the bot reads the device and **uploads a full snapshot**; the API reconciles its own state. Operator edits in the UI go **to the device first** (WebSocket), then the bot re-syncs so the API matches the radio again.

```mermaid
sequenceDiagram
  participant Radio as MeshCore_device
  participant Bot as meshflow_bot
  participant API as meshflow_api
  participant UI as meshflow_ui

  Note over Radio,API: On bot start
  Bot->>Radio: read channel table
  Bot->>API: POST mc-channel-sync
  API->>API: reconcile MessageChannel + mc_channels

  Note over UI,Radio: Optional operator edit
  UI->>API: apply to radio (WS)
  API->>Bot: apply_mc_channel_config
  Bot->>Radio: write channels
  Bot->>API: POST mc-channel-sync
```

**Drift:** if the API mirror and device disagree (e.g. failed push), the **next connect sync overwrites the API** from the device. No three-way merge in v1.

The bot starts **`MeshflowWSClient`** for MeshCore when `STORAGE_API_ROOT` + token are set (WebSocket URL derived from the API base URL unless `MESHFLOW_WS_URL` is set). The feeder’s 12-hex pubkey prefix is appended automatically on connect (not an operator env var).

### Horizontal scaling (API web tier)

Apply and traceroute commands use **Django Channels + Redis DB 0** ([`docs/REDIS.md`](../../REDIS.md)), not in-process Django signals. Signals only run inside one Python process and do not reach other workers or hosts.

| Piece | Scales horizontally? |
|-------|----------------------|
| `POST apply-mc-channel-config` on any Gunicorn/Uvicorn worker | Yes — handler calls `channel_layer.group_send` via Redis |
| `feeder_ws_group_has_subscribers` on any worker | Yes — `channels_redis` stores group membership in Redis DB 0 |
| Bot `NodeConsumer` WebSocket | One connection per bot; must land on **some** ASGI instance in the deployment that shares that Redis |
| Browser UI WebSocket (`text_messages`, JWT) | Separate consumer/groups; unrelated to feeder commands |

You do **not** need a separate “signal” bus for multi-worker API: Redis channel layer already is that bus.

### Local API + pre-prod bot (common 503 cause)

Sharing **Postgres** and **Redis** is not enough if the **HTTP hosts differ**:

- UI / `apply-mc-channel-config` → `http://localhost:8000` (local Django)
- Bot → `STORAGE_API_ROOT=https://pre-prod…/api` and WebSocket to **pre-prod**

The bot registers in Redis group `node_mc_{uuid}` through **pre-prod’s** `NodeConsumer`. Local Django also reads Redis DB 0, so presence *can* work if both use the same `REDIS_HOST` / password and the managed node `internal_id` + `mc_pubkey` match the device. If local settings use **`InMemoryChannelLayer`** (tests only) or a different Redis DB/host, local apply always sees **503 feeder not connected** even though pre-prod logs show `MeshflowWSClient: connected`.

**Practical dev setups (pick one):**

1. Point **meshflow-ui** at pre-prod API (browser and bot share one deployment), or  
2. Point **bot** `STORAGE_API_ROOT` at local API and run bot + API locally, or  
3. Keep split hosts but verify local `CHANNEL_LAYERS` is `channels_redis` to the **same** Redis DB 0 as pre-prod.

**Implementation plan:** Cursor workspace plan `mc_text_textmessage_pipeline_2c3e9fb8.plan.md` (kept in sync with this file; **this doc is canonical** in git for operators and PRs).

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

**Not implemented yet.**

| Step | Behaviour |
|------|-----------|
| **On connect** | Read channel table from device (`meshcore` API — exact calls TBD in bot spike). `POST` full snapshot to API **`mc-channel-sync`**; API updates `MessageChannel` rows and `ManagedNode.mc_channels`. |
| **On UI “apply to radio”** | WebSocket `apply_mc_channel_config` → write device → re-read device → `POST mc-channel-sync` again. |
| **Channel types (v1)** | **public** and **hashtag** only ([#297](https://github.com/pskillen/meshflow-api/issues/297)). |

The bot does **not** treat API channel rows as authoritative on startup (no “pull API config and push to device” as the default path). Packet **upload** remains as in Phase 1.

**Example sync payload** (illustrative):

```json
{
  "channels": [
    { "mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC", "mc_hashtag": null },
    { "mc_channel_idx": 1, "name": "Galloway", "mc_channel_type": "HASHTAG", "mc_hashtag": "galloway" }
  ],
  "synced_at": "2026-05-20T12:00:00Z"
}
```

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

## meshflow-api — channel mirror and WebSocket (planned #297)

### Primary: `POST mc-channel-sync` (device → API)

- **Caller:** meshflow-bot with feeder Node API key (same key as ingest), after reading the device.
- **Body:** full channel list with `mc_channel_idx`, `name`, `mc_channel_type`, `mc_hashtag` per row; optional `synced_at`.
- **Effect:** upsert constellation-scoped `MessageChannel` rows; set `ManagedNode.mc_channels` to exactly match the snapshot (detach indices no longer on device; do not delete channels still referenced by stored packets).
- **Read:** `GET` managed node (owner JWT) returns nested `mc_channels` mirror for UI.

### Secondary: push UI intent → device

- **WebSocket** `apply_mc_channel_config` to connected MC feeder (pattern: Meshtastic remote traceroute in [`ws/tests/test_node_consumer.py`](../../../Meshflow/ws/tests/test_node_consumer.py)).
- Bot writes device, then **must** call `mc-channel-sync` so the API mirror stays aligned with the device.
- Optional ack events: `mc_channel_config_applied` / `mc_channel_config_failed`.

**Permissions:** sync endpoint accepts feeder key; read/apply-for-owner uses node owner or constellation editor.

**OpenAPI:** `mc-channel-sync`, nested `mc_channels` on `ManagedNode`, WS command schemas.

**Not v1:** API-only CRUD that changes the mirror without a device round-trip (would reintroduce drift).

---

## meshflow-ui

### Today

- **Meshtastic feeders:** [Node Settings](https://github.com/pskillen/meshflow-ui/blob/main/src/pages/user/NodeSettings.tsx) maps **slots 0–7** to constellation `MessageChannel` rows via `meshtastic_channel_*` PATCH fields.
- **MeshCore feeders:** no channel editor; MC map/nodes views do not configure channels.

### Implemented (#297)

When `ManagedNode.protocol === MESHCORE`:

- **Display** channel list from API mirror (populated after bot connect sync).
- **Edit** with explicit **“Apply to radio”** — does not assume API-only saves change the device.
- Fields: name, type (**Public** / **Hashtag**), hashtag, `mc_channel_idx` (from last sync).
- Show sync status / errors when bot offline or WS apply fails.

**Message history UI** for MC protocol filter is **out of scope** for #297 (separate epic/UI work); #296 only requires API list support for channel broadcast messages.

---

## Operator checklist

1. Create MC **constellation** and **ManagedNode** feeder ([feeder-bootstrap.md](feeder-bootstrap.md)).
2. Link **Node API key** via `NodeAuth` (one key per feeder recommended).
3. Configure bot env (`MESHCORE_UPLOAD_ENABLED`, storage API).
4. Start bot with upload enabled; on connect it syncs device channels to API. Optionally use UI to apply changes **to the radio**, then wait for re-sync.
5. Confirm `channel_message` ingest: `MeshCoreTextPacket` rows with `channel` FK and matching `mc_channel_idx`.
6. Confirm `TextMessage` rows appear on `GET /api/messages/text/?protocol=meshcore` for channel traffic.

---

## Implementation status summary

| Capability | Status |
|------------|--------|
| Bot upload `channel_text` / `contact_text` | **Done** (Phase 1) |
| API store `MeshCoreTextPacket` + observation | **Done** |
| `resolve_mc_channel` via feeder `mc_channels` | **Done** (API branch `api-296/paddy/mc-text-channels`) |
| `ManagedNode.mc_channels` + channel types | **Done** (API) |
| API `POST /api/meshcore/feeder/mc-channel-sync/` | **Done** (API) |
| `TextMessage` + `protocol` field + history filter | **Done** (API) [#296](https://github.com/pskillen/meshflow-api/issues/296) |
| Bot device → API `mc-channel-sync` on connect | **Done** (bot, same branch family) |
| Bot WS apply + re-sync after UI push | **Done** (bot) |
| UI MC channel mirror + apply-to-radio | **Done** (ui) |
| MC message history in UI | **Deferred** (epic #266 UI) |

---

## References

- [ADR-0002 — MC channel modelling](../packet-ingestion/adr/0002-mc-channel-modelling.md)
- [ADR-0003 — MC broadcast semantics](../packet-ingestion/adr/0003-mc-broadcast-semantics.md)
- [ADR-0001 — MC node identity](../packet-ingestion/adr/0001-mc-node-identity.md)
- [Packet ingestion — MeshCore section](../packet-ingestion/README.md)
- [Implementation plan — Phase 2.1+](implementation-plan.md)
- [API keys & WebSocket](../../API_KEYS.md)
