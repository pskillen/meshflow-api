# ADR-0004 — MeshCore deduplication key

**Status:** Accepted (partial — [#387](https://github.com/pskillen/meshflow-api/issues/387))
**Date:** 2026-05-12
**Tracking:** [meshflow-api#276](https://github.com/pskillen/meshflow-api/issues/276); cross-feeder channel dedup [#387](https://github.com/pskillen/meshflow-api/issues/387)

## Context

Meshtastic ingestion deduplicates on `(from_int, packet_id, rx_time window)` — see [`DEDUPLICATION.md`](../DEDUPLICATION.md). The window (`PACKET_DEDUP_WINDOW_MINUTES`, default 10) collapses observations of the same on-air transmission heard by multiple feeders into one `MtRawPacket` plus N `PacketObservation` rows.

MeshCore has no `packet_id` and no consistent sender id on every event. The Phase 0.4 captures (see [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md)) show:

- **`rx_log_data` carries a `pkt_hash`** — a 32-bit-ish integer derived by the radio decoder from the frame's contents. Sample: `"pkt_hash": 808099514` in [`docs/packets/meshcore/rx_log_data_text.json`](../../../packets/meshcore/rx_log_data_text.json). Every `rx_log_data` sample in the bundle has one.
- **Decoded text events (`channel_message`, `contact_message`) do not carry `pkt_hash`.** They are the radio's "I already decoded this for you" view of an `rx_log_data` it just processed. The companion typically emits both — an `rx_log_data` for the raw frame **and** a decoded `channel_message` / `contact_message` for the human-readable payload.
- **`advertisement`, `path_update`, `discover_response`, `control_data`, `messages_waiting`, `trace_data`** carry no `pkt_hash` either, but they are not directly comparable to `rx_log_data` — they are different `event_type`s of decoder output, not duplicates of the same wire frame.

The previous backend-migration plan proposed `(from_pubkey_hash, packet_hash, rx_time window)`. With ADR-0001 dropping `from_pubkey_hash` (not on the wire, replaced by `mc_pubkey_prefix` for identity), the proposed key becomes redundant on its second component: the wire `pkt_hash` is already derived from the sender + payload bytes by the radio decoder.

## Decision

1. **Primary MC dedup key:** `(pkt_hash, rx_time window)`.
   - `pkt_hash` is the on-wire identifier exposed by `rx_log_data.pkt_hash`. Stored on `MeshCoreRawPacket.pkt_hash` (`BigIntegerField`, indexed; widened from 32-bit because MC may flip the sign bit in JSON).
   - No `from_pubkey*` component. Two unrelated senders producing the same `pkt_hash` within the dedup window would collide, but `pkt_hash` is wide enough (~32 bits of entropy over decoded frame bytes) that the birthday probability over a country-mesh's traffic rate is negligible. We accept the residual risk; the dedup window bounds the impact to ≤ `MESHCORE_PACKET_DEDUP_WINDOW_MINUTES` of one frame.
2. **Window env var:** `MESHCORE_PACKET_DEDUP_WINDOW_MINUTES`, default `10`. Same default as MT for operator familiarity. Documented in `docs/ENV_VARS.md` (Phase 1 task).
3. **Match semantics** (mirrors `find_existing_packet` for MT):
   - Same `pkt_hash`.
   - Incoming `rx_time` within `window` of the existing row's `first_reported_time`.
   - Match ⇒ insert `MeshCorePacketObservation` against the existing `MeshCoreRawPacket`. No new raw row.
   - No match (or out of window) ⇒ insert a new `MeshCoreRawPacket` and its first observation.
   - Same `(observer, packet)` twice ⇒ idempotent; no second observation row.
4. **Decoded twins (`channel_message`, `contact_message`):**
   - These do not have `pkt_hash` from the companion, but they are a decoded view of an `rx_log_data` the companion *just* emitted (typically within the same callback tick).
   - **Storage rule:** `rx_log_data` is the authoritative `MeshCoreRawPacket` row. Decoded text events are stored as a `MeshCoreTextPacket` subclass row (Phase 1) **linked** to the raw row when we can match them, or stand-alone when we cannot.
   - **Matching decoded → raw** is best-effort: within a short window (default `MESHCORE_DECODED_TWIN_WINDOW_SECONDS = 5`), look back at recent `rx_log_data` rows from the same observer where `payload_typename = TEXT_MSG` and the decoded payload bytes are a substring of `rx_log_data.payload`. If a match is found, set `MeshCoreTextPacket.raw_packet_fk = <that raw row>`. If not, leave the FK null. **This match is informational, not part of dedup.**
   - **Decoded-only dedup:** the dedup key for a decoded event with no `pkt_hash` falls back to `(event_type, sha256(canonical payload), rx_time window)` to prevent counting the same decoded twin twice if the companion emits it twice. Stored as `MeshCoreRawPacket.surrogate_hash` (nullable BigInt). Only one of `pkt_hash` or `surrogate_hash` is set on a given row; a partial unique index enforces this.
5. **Non-text non-`rx_log_data` events** (`advertisement`, `path_update`, `discover_response`, `control_data`, `messages_waiting`, `trace_data`) follow the same surrogate-hash rule: their dedup key is `(event_type, sha256(canonical payload), rx_time window)`. These are infrequent enough that the collision risk of the surrogate hash is irrelevant in practice.
6. **Per-observer idempotency** (same as MT): `MeshCorePacketObservation` has a unique constraint on `(packet, observer)` so retries from the bot never create duplicates.

## Implementation ([#387](https://github.com/pskillen/meshflow-api/issues/387), partial)

Shipped in `meshcore_packets/services/dedup_key.py` + ingest serializer:

- **`MeshCoreRawPacket.pkt_hash`** stores the **resolved dedup key** on create (wire `pkt_hash` when present, otherwise computed).
- **`channel_text`** without wire hash: content key `SHA-256(channel_text|constellation_id|message_channel_id|sender_timestamp|text)` (canonical `MessageChannel.id` after `resolve_mc_channel`; `sender_timestamp` from nested capture payload, `0` if missing).
- **Cross-feeder:** same on-air channel post → one `MeshCoreTextPacket`, N `MeshCorePacketObservation`, one `TextMessage` (Meshtastic parity).
- **Not yet:** separate `surrogate_hash` column, partial unique index, `raw_packet_fk` decoded-twin linkage ([#276](https://github.com/pskillen/meshflow-api/issues/276)); `contact_text` cross-feeder dedup (follow-up).

## Consequences

- **`pkt_hash` is signed in JSON.** The sample shows a positive value, but the companion's encoding can produce values outside the `int32` positive range. Store as `BigIntegerField` and treat as opaque. Do not reinterpret the sign.
- **Cross-protocol dedup is impossible**, and we do not attempt it. An MT and an MC packet are never "the same" packet for dedup purposes — they are different protocols on different radios.
- **Decoded-twin linkage is best-effort.** Phase 1 ships with the matching helper; if it misses, the decoded text row exists without a raw FK and we still have the data. Phase 2 can revisit using `sender_timestamp` + observer correlation if the simple substring match proves too lossy.
- **No `from_pubkey_hash` index needed** for dedup. Identity indexes (`mc_pubkey`, `mc_pubkey_prefix`) are owned by ADR-0001 and serve identity queries, not dedup lookups.
- **Operational tuning:** as with MT, `MESHCORE_PACKET_DEDUP_WINDOW_MINUTES` is the single knob. We expect identical default behaviour because the on-air retransmit cadences are comparable; if Phase 1 acceptance shows otherwise, tune per-protocol.
- **Out of scope:** cross-environment dedup (prod + pre-prod). MT already keeps these separate per instance (see `DEDUPLICATION.md`); MC follows the same rule.

## Evidence

- [`docs/packets/meshcore/rx_log_data_text.json`](../../../packets/meshcore/rx_log_data_text.json) — `"pkt_hash": 808099514`, `route_typename: "FLOOD"`, `payload_typename: "TEXT_MSG"`.
- [`docs/packets/meshcore/rx_log_data_advert.json`](../../../packets/meshcore/rx_log_data_advert.json), [`rx_log_data_path.json`](../../../packets/meshcore/rx_log_data_path.json), [`rx_log_data_req.json`](../../../packets/meshcore/rx_log_data_req.json), [`rx_log_data_control.json`](../../../packets/meshcore/rx_log_data_control.json) — all carry `pkt_hash`.
- [`docs/packets/meshcore/channel_message/20260507_094921_075978.json`](../../../packets/meshcore/channel_message/20260507_094921_075978.json), [`contact_message/20260506_205758_541689.json`](../../../packets/meshcore/contact_message/20260506_205758_541689.json) — no `pkt_hash`; decoded views only.
- Field reference: [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md) (`rx_log_data` common fields — `pkt_hash`).
- MT contract for comparison: [`DEDUPLICATION.md`](../DEDUPLICATION.md).
