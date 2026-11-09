# ADR-0005 — Feeder-scoped authentication (one API key per feeder)

**Status:** Accepted. The Meshtastic v4 URLs and the number-change flow are built (below); the MeshCore v4 URLs are deferred.
**Built (API):** the Meshtastic and shared v4 URLs (`identity/`, `bot-version/`, `meshtastic/ingest/`, `meshtastic/nodes/`) with single-feeder auth and its three codes, `ws/nodes/?feeder_scoped=1`, the Prometheus usage metrics and `ManagedNode` usage fields (decision 5), recording of the reported node number (decision 3), and the re-key decision logic with its audit model, behind `MESHTASTIC_FEEDER_AUTO_REKEY` (decision 8), the owner's Discord DM, the event list and acknowledge API, and the manual re-point. Not built: the MeshCore v4 URLs (deferred), the bot side, and blocking new shared links (7).
**Date:** 2026-11-02
**Tracking:** [meshflow-api#438](https://github.com/pskillen/meshflow-api/issues/438); epic [meshflow-api#437](https://github.com/pskillen/meshflow-api/issues/437)

## Context

Today a `NodeAPIKey` can be linked to several feeders (`NodeAuth` is many-to-many between key and `ManagedNode`). Because of that, the feeder's node number in the URL (`/api/packets/{node_id}/ingest/`, and the v3 equivalents) is what says which feeder is posting, and `NodeAuthorizationPermission` authorises on the pair (key, node number). `ws/consumers.py` and `common/meshtastic_feeder_auth.py` resolve a feeder the same way, and the Meshtastic WebSocket group is named after the node number (`common/ws_groups.py`).

Meshtastic 2.8 sets a node's number to `crc32(public_key)` (see [ADR-0006](0006-meshtastic-identity-linking.md)), so an **upgraded feeder's number changes**. The bot would then post under a number its key is not linked to, get a 403 and stop ingesting, silently. The node number is a poor thing to authorise on.

MeshCore already has the same sharing problem and works around it with the `X-MeshCore-Feeder-Pubkey` header.

## Decision

Planned, in order:

1. **One API key per feeder.** A key linked to exactly one `ManagedNode` identifies that feeder on its own. The rule is one key per `ManagedNode` whatever the protocol; the key's single node decides the protocol. A bot running two radios is two processes and needs two keys.
2. **Keys are rotatable, and a feeder may hold two keys during a rotation.** The eventual schema constraint is unique on `NodeAuth.api_key` only (a key has one feeder; a feeder may have two keys), so rotation needs no downtime.
3. **The reported node number is never used for authorisation.** On v4 URLs it can drive the gated re-key (decision 8). The bot reports its number, public key and firmware in headers (`X-Meshtastic-Feeder-Pubkey`, `-Node-Num`, `-Firmware`). The API records them; it does not authorise on them. A reported number that differs from the stored one is **flagged, not rejected**: ingest continues under the feeder the key identifies, and the event is recorded for review. The likely cause of a mismatch is a bot config copied onto another radio.
4. **New v4 feeder URLs under `/api/v4/feeder/`**, with no node number in the path:
   - shared: `identity/` (GET), `bot-version/`
   - Meshtastic: `meshtastic/ingest/`, `meshtastic/nodes/`
   - MeshCore: `meshcore/ingest/`, `meshcore/mc-channel-sync/`, `meshcore/bot-config/`

   They authenticate with `NodeAPIKeyAuthentication` plus a feeder-scoped permission that requires the key to have exactly one active feeder of the right protocol. Stable error codes: `feeder_not_linked`, `shared_api_key` (403, telling the owner to mint a per-feeder key), `feeder_protocol_mismatch`. The WebSocket accepts `feeder_scoped=1` and no node id. The group name moves to the `ManagedNode` internal id so a number change cannot orphan connected bots.
5. **Legacy URLs are kept and tracked.** v1/v2/v3 URLs behave exactly as today, shared keys included, until they are unused; then they are removed (this joins up with retiring the v1 ingest URLs, [meshflow-api#319](https://github.com/pskillen/meshflow-api/issues/319)). Usage is tracked in Prometheus (request counts per API generation, endpoint and status class; auth rejections by code) plus nullable fields on `ManagedNode` recording which API generation a feeder last used and when it last used a legacy URL (written at most every 10 minutes), so staff can list the feeders still on legacy URLs. Per-feeder Prometheus labels are not used: the DB fields survive restarts.
6. **The bot probes v4 by default and falls back.** For each storage destination it probes `GET /api/v4/feeder/identity/` at start and hourly: 200 uses v4; 404 (older API) uses legacy; 403 `shared_api_key` uses legacy and logs an error asking for a per-feeder key. Destinations are independent, so a bot feeding prod and pre-prod can be on different generations.
7. **No new shared links.** The UI, key-create serializer and admin form refuse to link a key that already has an active link. Existing links keep working on legacy URLs.
8. **Auto re-key is gated.** When the reported number differs, `crc32(reported key)` equals the new number and the key is the one already trusted for this feeder (below), the API updates `meshtastic_node_id` atomically and writes an audit row (`ManagedNodeIdentityEvent`). The crc32 relationship is **confirmed on hardware**. Because **public keys are not unique** (one key sits on 17+ unrelated nodes), a key held by any other node, or a number held by another active feeder, is flagged and nothing changes. It runs on v4 URLs only and is behind **`MESHTASTIC_FEEDER_AUTO_REKEY`** (default off; the owner's Discord DM and the manual re-point `POST /api/nodes/managed-nodes/{internal_id}/repoint-meshtastic-id/` are built, so it can be enabled). With it off, a provable change is still flagged and ingest still continues.

   **Threat model.** A client holding the feeder's API key controls both the number and the key it reports, and crc32 is forgeable (28 chosen bytes plus 4 solved ones hit any number), so a match proves consistency, not ownership. The API therefore flags, and never applies, when: the reported key differs from the stored key; the feeder has no stored key; the stored key was recorded from a report within the last hour; an `ObservedNode` at the target number has a different key, or is claimed by someone else; or the number is outside the valid range (below 4, or `0xFFFFFFFF`). A key reported on an unchanged number never replaces a stored one. The residual risk: a client with the API key of a feeder that has no stored key can record a forged key, wait out the hour (recording is not gated by `MESHTASTIC_FEEDER_AUTO_REKEY`, so the hour can be spent before the flag goes on), and move that feeder to any unclaimed number. The check on the target's key guards against accidents only: NodeDB uploads are client-writable, so the same client can overwrite that key first. It is one shot per feeder, since the first key can't be replaced, and the event is audited. It cannot touch a claimed node or an active feeder, and a key that came from a report never claims the target row, so the move gains no edit rights over it.

## Consequences

- An upgraded feeder on a v4 URL keeps ingesting even before its number is re-pointed. A feeder on a **legacy** URL cannot survive an upgrade, by design: it must be on a per-feeder key and a bot that uses v4 first (see the [upgrade runbook](../meshtastic-2.8-upgrade-runbook.md)).
- Owners with shared keys must mint per-feeder keys. Prod needs a read-only report of keys linked to more than one feeder or across protocols; the counts are not yet known.
- A feeder whose `ManagedNode` has no stored key records the first key it reports on its current number (a `key_changed` audit event dates it), unless the feeder's own `ObservedNode` row holds a different key. That key cannot back a number change until it is an hour old.
- A new number may collide with another active `ManagedNode` (partial unique constraint); that case is flagged, not applied.
- The schema constraint (unique on `NodeAuth.api_key`) comes last, once legacy URLs are gone.
- Out of scope: the identity link between old and new `ObservedNode` rows (ADR-0006), and any change to legacy URL behaviour.

## Evidence

- Current code paths: `nodes/permissions.py` (`NodeAuthorizationPermission`), `packets/views.py` (`PacketIngestView`, node upsert check), `common/meshtastic_feeder_auth.py`, `common/meshcore_feeder_auth.py`, `common/ws_groups.py`, `ws/consumers.py`.
- Firmware: `NodeDB.cpp:543` (`my_node_num = crc32(public_key)`), see ADR-0006.
- Existing docs: [README](../README.md) (endpoint and authentication), [API_KEYS.md](../../../API_KEYS.md).
