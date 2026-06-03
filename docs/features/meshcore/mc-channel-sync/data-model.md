# mc-channel-sync — data model

Purpose: which database rows exist for MeshCore channels, and how snapshot entries map to them.

Normative design: [ADR-0002](../../packet-ingestion/adr/0002-mc-channel-modelling.md).

---

## Two layers

```text
Constellation
  └── MessageChannel (canonical, protocol=MESHCORE)
        ▲
        │ FK message_channel
ManagedNode (feeder) ── ManagedNodeMcChannelLink ── mc_channel_idx (device slot)
```

| Layer | Model | Scoped by | Holds device index? |
|-------|--------|-----------|---------------------|
| **Canonical** | `MessageChannel` | `constellation` | No |
| **Feeder mirror** | `ManagedNodeMcChannelLink` | `managed_node` | Yes (`mc_channel_idx`, unique per feeder) |

The same logical channel (e.g. hashtag `galloway`) is **one** `MessageChannel` row even when two feeders use different device indices. Each feeder has its own link row pointing at that canonical row.

Meshtastic channels on the same table use `protocol=MESHTASTIC` and `ManagedNode.meshtastic_channel_0..7` — not the MC link table.

---

## `MessageChannel` (canonical)

Django: [`Meshflow/constellations/models.py`](../../../Meshflow/constellations/models.py)

| Field | MC usage |
|-------|----------|
| `name` | Operator-facing label; for `HASHTAG`, typically the tag without `#` |
| `constellation` | FK |
| `protocol` | `MESHCORE` (2) |
| `mc_channel_type` | `PUBLIC` (1) or `HASHTAG` (2) |
| `mc_hashtag` | Lowercase tag when `HASHTAG`; null for `PUBLIC` |

**Uniqueness (MC rows):**

| Type | Constraint |
|------|------------|
| `HASHTAG` | Unique `(constellation, protocol, mc_hashtag)` where hashtag set |
| `PUBLIC` | Unique `(constellation, protocol, name)` for public rows |

`MeshCoreMessageChannel` is a **proxy model** for admin listing MC rows only.

**Not stored on canonical rows:** `mc_channel_idx`, PSK, channel secret (MeshCore companion stores secrets on device; not mirrored in API v1).

**Planned ([#391](https://github.com/pskillen/meshflow-api/issues/391)):** `region_scope` on canonical rows; drop `mc_hashtag` in favour of `name` for hashtags.

---

## `ManagedNodeMcChannelLink`

Django: [`Meshflow/nodes/models.py`](../../../Meshflow/nodes/models.py)

| Field | Description |
|-------|-------------|
| `managed_node` | MeshCore feeder |
| `message_channel` | Canonical `MessageChannel` |
| `mc_channel_idx` | Device slot 0–63 |

Unique: `(managed_node, mc_channel_idx)`.

`ManagedNode.mc_channels` is the M2M through this table. `ManagedNode.mc_channels_synced_at` is updated on every successful reconcile.

---

## Snapshot → canonical mapping

[`upsert_canonical_mc_channel`](../../../Meshflow/meshcore_packets/services/channel_identity.py):

| `mc_channel_type` | Match key | `defaults` |
|-------------------|-----------|------------|
| `HASHTAG` | `(constellation, protocol, mc_hashtag)` normalized from `mc_hashtag` or `name` | `name` display string |
| `PUBLIC` | `(constellation, protocol, name)` normalized | `mc_hashtag=null` |

Invalid hashtag (empty after normalize) → `ValueError` → sync `400`.

---

## Placeholder channels (ingest before sync)

[`placeholder_canonical_mc_channel`](../../../Meshflow/meshcore_packets/services/channel_identity.py) creates:

- `name`: `MC channel {idx}`
- `mc_channel_type`: `PUBLIC`
- Link row for `(observer, channel_idx)`

Reconcile replaces the link’s `message_channel` when the device reports real metadata for that slot. Orphan placeholders may remain in the catalog if never configured on device.

---

## API serialization surfaces

| Surface | Serializer | Contents |
|---------|------------|----------|
| Sync request | `McChannelSnapshotEntrySerializer` | Device snapshot entries |
| Sync response / managed node | `FeederMcChannelMirrorSerializer` | Canonical `id`, `name`, `mc_channel_type`, `mc_hashtag`, plus `mc_channel_idx` from link |
| Constellation nested | `message_channel_payload` in `constellations/serializers.py` | Includes `display_label` from `mc_channel_display_label` |
| Apply payload | `McChannelApplyEntrySerializer` | Same entry shape; validated hashtag rules |

`display_label` is read-only on API responses (`#tag` for hashtags).

---

## Related

- [flow.md](flow.md) — reconcile algorithm and endpoints
- [text-message-channels.md](../text-message-channels.md) — `MeshCoreTextPacket.channel`, `TextMessage`
