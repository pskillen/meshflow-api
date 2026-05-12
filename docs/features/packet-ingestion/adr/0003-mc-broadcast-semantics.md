# ADR-0003 — MeshCore broadcast vs directed semantics

**Status:** Proposed
**Date:** 2026-05-12
**Tracking:** [meshflow-api#276](https://github.com/pskillen/meshflow-api/issues/276)

## Context

Meshtastic represents broadcast destinations with the sentinel value `to_int == 0xFFFFFFFF`. The API and downstream features (text messages, traceroute, mesh monitoring, DX) rely on that single sentinel to distinguish a broadcast from a directed transmission.

MeshCore has no such sentinel. From the Phase 0.4 captures (see [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md)):

- `channel_message` (`type=CHAN`) — group/channel text. Carries `channel_idx`, `path_hash_mode`, `path_len`, `txt_type`, `sender_timestamp`, `text`. **Does not carry any destination identifier.** Every channel_message is implicitly a broadcast on that channel.
- `contact_message` (`type=PRIV`) — DM text. Carries `pubkey_prefix` of the **sender** (12-hex) plus body. **No destination field either**, because the local companion received it; the destination is "me" (the connected radio).
- `rx_log_data` — route metadata: `route_type` (numeric) and `route_typename` (`FLOOD`, `TC_FLOOD`, `DIRECT`). These describe **how the frame is forwarded**, not who it is for. A `DIRECT` can be unicast or a fragment of a flood; a `FLOOD` can still carry a directed payload (the radio still forwards it to neighbours).
- No event in the bundle carries a `to_pubkey` or `to_pubkey_hash` field.

We therefore need an unambiguous, capture-supported way to mark "this on-air transmission was a broadcast" without inventing wire fields. We also want to avoid baking the MT sentinel pattern into MC schema (no `0xFFFF...` magic value over a key field that has no defined width on the wire).

## Decision

1. **`MeshCoreRawPacket.to_pubkey`** — `CharField(max_length=64)`, hex, nullable. Set only when the wire / decoded event names a specific recipient. **In Phase 0.4 captures this is always `NULL`.**
2. **`MeshCoreRawPacket.to_pubkey_prefix`** — `CharField(max_length=12)`, hex, nullable. Same rule.
3. **Broadcast indicator = absence.** A row is broadcast iff `to_pubkey IS NULL AND to_pubkey_prefix IS NULL`. **No sentinel value is introduced.** Code that asks "is this a broadcast?" reads:

   ```python
   is_broadcast = packet.to_pubkey is None and packet.to_pubkey_prefix is None
   ```

4. **Per-event mapping (Phase 1):**

   | MC event / decode | Stored as | Direction |
   | --- | --- | --- |
   | `channel_message` (`type=CHAN`) | `MeshCoreTextPacket` with `to_pubkey = NULL` and the resolved `MessageChannel` FK | broadcast |
   | `contact_message` (`type=PRIV`) | `MeshCoreTextPacket` with `to_pubkey_prefix = <observer's own pubkey prefix>` | directed (to us) |
   | `rx_log_data` (`TEXT_MSG`, `ADVERT`, `PATH`, `REQ`, `CONTROL`, …) | `MeshCoreRawPacket`; `to_pubkey*` only populated if the decoded payload exposes a recipient | usually broadcast (advert, path, control); directed for `REQ`/`RESP` if the decoder yields one |

5. **`route_type` / `route_typename` are preserved** on `MeshCoreRawPacket` as descriptive columns (`route_type` IntegerChoices, `route_typename` CharField for forward-compat). They are **not** used as the broadcast indicator. The names are stored to keep raw-log inspection useful without a lookup table; downstream code should branch on `route_type` (the integer) when needed.
6. **`MessageChannel` FK on the observation** stays the way a broadcast is *attributed* to a channel. A broadcast `channel_message` has `to_pubkey IS NULL` AND `MeshCorePacketObservation.channel` set. A directed `contact_message` has `to_pubkey_prefix` set AND `MeshCorePacketObservation.channel = NULL` (DM has no channel).
7. **Cross-protocol query convenience.** For mixed-protocol surfaces (UI, stats), the protocol-agnostic broadcast predicate is:
   - MT: `to_int == 0xFFFFFFFF`
   - MC: `to_pubkey IS NULL AND to_pubkey_prefix IS NULL`

   Expose this as an `is_broadcast` `@property` on each raw-packet model, and as a `BooleanField`-style annotation on serializers, rather than a stored column. Avoid leaking the MT sentinel into MC code paths.

## Consequences

- **No sentinel magic for MC.** Future firmware that does add a recipient field can populate `to_pubkey*` without a schema break. The "broadcast == NULL" rule continues to hold.
- **`is_broadcast` is a derived value** in two places (one per protocol). The risk of drift is small because each protocol's model owns its own predicate; cross-protocol code uses a tiny helper rather than a shared column.
- **`route_typename` is informational, not a contract.** Downstream apps must not branch on the string. If we later need a stable enum, we already have `route_type` (the integer).
- **DM-to-someone-else.** In the rare case the local companion observes a DM addressed to a different node (unusual on MC because PRIV is decrypted locally to "me"), the serializer leaves `to_pubkey*` `NULL`. We choose "unknown directed recipient" over inventing one. Phase 2 may revisit if we see such events in the wild.
- **Out of scope:** ACK / REQ / RESP recipient extraction — depends on Phase 2 subclass decoders. ADR-0003 only commits to the storage shape; those subclasses will populate `to_pubkey*` when their decoders produce one.

## Evidence

- [`docs/packets/meshcore/channel_message/20260507_094921_075978.json`](../../../packets/meshcore/channel_message/20260507_094921_075978.json) — no destination field; only `channel_idx`.
- [`docs/packets/meshcore/contact_message/20260506_205758_541689.json`](../../../packets/meshcore/contact_message/20260506_205758_541689.json) — `pubkey_prefix` is the sender, not the recipient.
- [`docs/packets/meshcore/rx_log_data_text.json`](../../../packets/meshcore/rx_log_data_text.json), [`rx_log_data_advert.json`](../../../packets/meshcore/rx_log_data_advert.json), [`rx_log_data_path.json`](../../../packets/meshcore/rx_log_data_path.json), [`rx_log_data_req.json`](../../../packets/meshcore/rx_log_data_req.json), [`rx_log_data_control.json`](../../../packets/meshcore/rx_log_data_control.json) — `route_type` / `route_typename` present; no recipient field on any of them.
- Field reference: [`MESHCORE_PACKET_FIELDS.md`](../MESHCORE_PACKET_FIELDS.md) (`channel_message`, `contact_message`, `rx_log_data`).
