# ADR-0002 — MeshCore channel modelling

**Status:** Accepted (amended 2026-06-01)
**Date:** 2026-05-12
**Tracking:** [meshflow-api#276](https://github.com/pskillen/meshflow-api/issues/276), [meshflow-api#379](https://github.com/pskillen/meshflow-api/issues/379)

## Context

Meshtastic models channels as a fixed-size, named, ordered slot table on each radio. The API mirrors this with `MessageChannel` plus eight `ManagedNode.channel_0..channel_7` foreign keys, and `PacketObservation.channel` resolves a packet's channel index against the observer's slot table.

MeshCore does not have an equivalent on-wire concept. From the Phase 0.4 captures (see [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md)):

- `channel_message` carries `payload.channel_idx` (zero-based integer) and `path_hash_mode` / `path_len`, but **no channel name and no channel hash**.
- No other event in the bundle (`advertisement`, `path_update`, `discover_response`, `rx_log_data`, `contact_message`, `control_data`, `trace_data`, `messages_waiting`) carries any channel-related identifier.
- MC channel names ("Public", "Galloway", etc.) are an operator/configuration concept on the companion device; they are not transmitted.

The earlier plan proposed `MessageChannel.mc_channel_hash`. We have no on-wire evidence for one in this firmware (1.15.0). Adding a column we never populate produces dead schema; deferring it costs nothing because the index is the dispatch key.

We still need a way to:

- Resolve `(observer, channel_idx)` → a `MessageChannel` row for `PacketObservation`.
- Associate `ManagedNode` rows with the channels they participate in, since MC has no fixed 0..7 slot mapping.

## Decision

1. **Add `MessageChannel.protocol`** (same enum as `ObservedNode.protocol`). Channels are single-protocol; an MT channel and an MC channel are distinct rows even if their names happen to match.
2. **Canonical `MessageChannel` rows (constellation-scoped logical identity):**
   - `name`, `mc_channel_type` (`PUBLIC` / `HASHTAG`), `mc_hashtag` (when HASHTAG).
   - **No `mc_channel_idx` on `MessageChannel`.** Device slot index is per-feeder, not global.
   - Uniqueness: `(constellation, protocol, mc_hashtag)` for HASHTAG rows; `(constellation, protocol, name)` for PUBLIC rows (normalized in services).
3. **Defer `mc_channel_hash`.** Revisit if/when a firmware revision starts emitting one on the wire. No column added now.
4. **Per-feeder slot mapping via `ManagedNodeMcChannelLink` (M2M through table):**
   - `managed_node`, `message_channel` (canonical), `mc_channel_idx` (`0..63`, unique per managed node).
   - `ManagedNode.mc_channels` — `ManyToManyField(MessageChannel, through='ManagedNodeMcChannelLink', ...)`.
   - Meshtastic `meshtastic_channel_0..7` FKs stay MT-only and untouched.
5. **Channel resolution on ingest** (`resolve_mc_channel(observer, channel_idx)`):
   - Look up `ManagedNodeMcChannelLink` for `(observer, channel_idx)` → canonical `MessageChannel`.
   - If missing (heard before sync), create placeholder canonical + link; overwritten when device sync supplies real metadata.
6. **`TextMessage.channel` and packet FKs point at the canonical row** so the same logical channel (`#test`) is one row even when two feeders use different device indices.

## Consequences

- **Operators name MC channels manually.** No automatic name discovery (none on the wire); the auto-created `"MC channel N"` placeholder is good enough until someone updates it.
- **No backfill needed** for existing data — MC is greenfield in this codebase.
- **`mc_channels` M2M lets a managed node "subscribe" to an arbitrary subset of MC channels**, which fits the protocol better than 8 fixed slots. UI and admin screens for `ManagedNode` need a small per-protocol branch.
- **If MC firmware later adds a channel hash on the wire**, we can add `mc_channel_hash` and a matching unique constraint without touching the dispatch path — `channel_idx` continues to be the primary dispatch key.
- **Risk:** auto-creating `MessageChannel` rows on first sight could pollute the table if an attacker sends bogus channel indices via a compromised observer. Mitigation: limit to indices `0..63` (MC's plausible range) and require channel rows to be attached to the **observer's** `mc_channels` only on packets the observer authenticated for — which they already are.
- **Out of scope:** UI for managing `mc_channels` per managed node; covered in Phase 1.7 (UI ticket).

## Supplement (2026-05-20) — device as source of truth for operator metadata

ADR §5–6 still govern **ingest resolution** (`channel_idx` on wire → canonical `MessageChannel` via `ManagedNodeMcChannelLink`). For **name**, **type** (public/hashtag), and **hashtag string**, Phase 2 ([#297](https://github.com/pskillen/meshflow-api/issues/297)) treats the **MeshCore companion channel table** as authoritative:

- On bot connect, the bot uploads a full device snapshot; the API **reconciles** canonical `MessageChannel` rows and per-feeder links (see [`text-message-channels.md`](../../meshcore/text-message-channels.md)).
- UI edits push to the device (WebSocket), then the bot re-syncs; the API does not rely on API-only CRUD as the long-term source of names.
- Auto-created `"MC channel N"` placeholders at ingest (before first sync) remain; they are overwritten when sync supplies device metadata.

This does not change the wire model (index-only) or constellation scoping.

## Evidence

- [`docs/packets/meshcore/channel_message/20260507_094921_075978.json`](../../../packets/meshcore/channel_message/20260507_094921_075978.json) — shows `channel_idx`, no name, no hash.
- [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md) — `channel_message` section.
- Absence: grepping the Phase 0.4 capture tree ([`meshflow-bot/docs/meshcore_packets/`](https://github.com/pskillen/meshflow-bot/tree/main/docs/meshcore_packets)) for `channel_hash`, `channel_name`, or `chan_id` returns no matches.
