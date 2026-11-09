# ADR-0005 — Feeder-scoped authentication (one API key per feeder)

**Status:** Proposed. Describes **planned** behaviour; parts are built (below), the rest is not.
**Built (API):** the Meshtastic and shared v4 URLs (`identity/`, `bot-version/`, `meshtastic/ingest/`, `meshtastic/nodes/`) with single-feeder auth and its three codes, `ws/nodes/?feeder_scoped=1`, the Prometheus usage metrics and `ManagedNode` usage fields (decision 5), recording of the reported node number (decision 3), and the re-key decision logic with its audit model, behind `MESHTASTIC_FEEDER_AUTO_REKEY` (decision 8; the owner notice and manual re-point follow). Not built: the MeshCore v4 URLs, the bot side, and blocking new shared links (7).
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
3. **The reported node number is informational.** The bot reports its number, public key and firmware in headers (`X-Meshtastic-Feeder-Pubkey`, `-Node-Num`, `-Firmware`). The API records them; it does not authorise on them. A reported number that differs from the stored one is **flagged, not rejected**: ingest continues under the feeder the key identifies, and the event is recorded for review. The likely cause of a mismatch is a bot config copied onto another radio.
4. **New v4 feeder URLs under `/api/v4/feeder/`**, with no node number in the path:
   - shared: `identity/` (GET), `bot-version/`
   - Meshtastic: `meshtastic/ingest/`, `meshtastic/nodes/`
   - MeshCore: `meshcore/ingest/`, `meshcore/mc-channel-sync/`, `meshcore/bot-config/`

   They authenticate with `NodeAPIKeyAuthentication` plus a feeder-scoped permission that requires the key to have exactly one active feeder of the right protocol. Stable error codes: `feeder_not_linked`, `shared_api_key` (403, telling the owner to mint a per-feeder key), `feeder_protocol_mismatch`. The WebSocket accepts `feeder_scoped=1` and no node id. The group name moves to the `ManagedNode` internal id so a number change cannot orphan connected bots.
5. **Legacy URLs are kept and tracked.** v1/v2/v3 URLs behave exactly as today, shared keys included, until they are unused; then they are removed (this joins up with retiring the v1 ingest URLs, [meshflow-api#319](https://github.com/pskillen/meshflow-api/issues/319)). Usage is tracked in Prometheus (request counts per API generation, endpoint and status class; auth rejections by code) plus nullable fields on `ManagedNode` recording which API generation a feeder last used and when it last used a legacy URL (written at most every 10 minutes), so staff can list the feeders still on legacy URLs. Per-feeder Prometheus labels are not used: the DB fields survive restarts.
6. **The bot probes v4 by default and falls back.** For each storage destination it probes `GET /api/v4/feeder/identity/` at start and hourly: 200 uses v4; 404 (older API) uses legacy; 403 `shared_api_key` uses legacy and logs an error asking for a per-feeder key. Destinations are independent, so a bot feeding prod and pre-prod can be on different generations.
7. **No new shared links.** The UI, key-create serializer and admin form refuse to link a key that already has an active link. Existing links keep working on legacy URLs.
8. **Auto re-key is gated.** When the reported number differs, `crc32(reported key)` equals the new number and the key matches the stored `ManagedNode` key (a blank stored key is trusted on first use), the API updates `meshtastic_node_id` atomically and writes an audit row (`ManagedNodeIdentityEvent`). The crc32 relationship is **confirmed on hardware**. Because **public keys are not unique** (one key sits on 17+ unrelated nodes), a key held by any other node, or a number held by another active feeder, is flagged and nothing changes. It runs on v4 URLs only and is behind **`MESHTASTIC_FEEDER_AUTO_REKEY`** (default off; owner notification and manual re-point arrive in a follow-up and must ship before it is enabled in production). With it off, a provable change is still flagged and ingest still continues.

## Consequences

- An upgraded feeder on a v4 URL keeps ingesting even before its number is re-pointed. A feeder on a **legacy** URL cannot survive an upgrade, by design: it must be on a per-feeder key and a bot that uses v4 first (see the [upgrade runbook](../meshtastic-2.8-upgrade-runbook.md)).
- Owners with shared keys must mint per-feeder keys. Prod needs a read-only report of keys linked to more than one feeder or across protocols; the counts are not yet known.
- A feeder whose `ManagedNode` has no stored key is trusted on first use, and the reported key is stored. Acceptable because the caller already holds the feeder's key.
- A new number may collide with another active `ManagedNode` (partial unique constraint); that case is flagged, not applied.
- The schema constraint (unique on `NodeAuth.api_key`) comes last, once legacy URLs are gone.
- Out of scope: the identity link between old and new `ObservedNode` rows (ADR-0006), and any change to legacy URL behaviour.

## Evidence

- Current code paths: `nodes/permissions.py` (`NodeAuthorizationPermission`), `packets/views.py` (`PacketIngestView`, node upsert check), `common/meshtastic_feeder_auth.py`, `common/meshcore_feeder_auth.py`, `common/ws_groups.py`, `ws/consumers.py`.
- Firmware: `NodeDB.cpp:543` (`my_node_num = crc32(public_key)`), see ADR-0006.
- Existing docs: [README](../README.md) (endpoint and authentication), [API_KEYS.md](../../../API_KEYS.md).
