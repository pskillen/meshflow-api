# ADR-0006 — Meshtastic identity linking (2.7 to 2.8 node numbers)

**Status:** Proposed. Describes **planned** behaviour; none of it is built yet. The central assumption (zlib `crc32` equals the firmware's value) is **not yet verified on hardware**.
**Date:** 2026-11-02
**Tracking:** [meshflow-api#439](https://github.com/pskillen/meshflow-api/issues/439) (predicted ids); epic [meshflow-api#437](https://github.com/pskillen/meshflow-api/issues/437)

## Context

In Meshtastic 2.8 a node's number is the CRC-32 of its 32-byte Curve25519 public key (firmware `NodeDB.cpp:543`, `createNewIdentity()`). Until 2.7 the number was usually derived from the MAC (`mac[2..5]`). Facts from the firmware source at `v2.8.2` (read from source, not yet exercised on hardware):

- An upgrade **reuses the existing private key**, so the new number is **predictable from a public key we already store**.
- A key is minted only once a region is set; with the region unset the number stays MAC-based. A key minted mid-session changes the number without a reboot.
- A **full erase rotates the key** (and so the number). Known low-entropy keys, unclamped keys and licensed nodes (no key in 2.7) also get a new key.
- Over-the-air NodeInfo still carries `macaddr`. The feeder's NodeDB-to-client path zero-fills it for other nodes (only the local node keeps it).
- 2.8 receivers enforce `crc32(user.public_key) == from` on first-contact signed NodeInfo.

Consequence for Meshflow: after an upgrade the node appears as a **new** `ObservedNode`, the old one goes silent (and mesh monitoring would raise false offline alerts), and claims, watches, DX metadata and RF profile stay on the old row. History splits because `from_int` and `relay_node` are raw numbers. `ObservedNode.meshtastic_public_key` is stored in mixed formats (base64 and hex).

## Decision

Planned:

1. **Predict ahead of the upgrade.** Normalise every stored key (base64 or hex to 64-char hex; anything not 32 bytes yields null, never an error) and store `crc32` of it as `meshtastic_key_node_id` (indexed) on `ObservedNode`, with the same on `ManagedNode.meshtastic_public_key`. An idempotent backfill reads `ObservedNode.meshtastic_public_key`, falling back to the latest `NodeInfoPacket.public_key` for that `from_int`, and reports keys shared by several nodes. Worked example under test: `!da545c78` is predicted to become `!4396524c` (unverified).
2. **Best-effort linking of old and new identities, never merging.** Both `ObservedNode` rows are kept; a `MeshtasticIdentityLink(old, new, evidence, confidence, state)` row is the alias. `from_int` is never rewritten, so rollback is deleting link rows. Evidence:
   - **Strong, automatic:** the same public key K, `crc32(K)` equals the new number, and exactly one old Meshtastic node holds K. Two active nodes sharing a key are flagged, not linked.
   - **Medium, suggested and needing confirmation:** the OTA `macaddr` M satisfies `int(M[2:6]) == old number` (or the MAC equals the stored `mac_addr`). This covers full erases and licensed nodes.
   - **Weak, hint only:** names, hardware model, location.
3. **A full erase is a new identity.** It rotates the key, so there is no key-based link and no prediction. Only the MAC signal can propose a link, and it needs confirmation. The upgrade runbook therefore says **never full-erase a feeder**.
4. **Managed feeders** are handled by [ADR-0005](0005-feeder-scoped-auth.md): the `ManagedNode` row is re-pointed (so observer foreign keys stay intact), and a `ManagedNodeIdentityEvent` is the audit alias. When that happens the `ObservedNode` link is created with evidence `managed_feeder_rekey`.
5. **Do not clobber identity.** NodeInfo ingest must ignore a blank or zero MAC, never replace a name with its own 24-byte prefix, never clear a stored key, and prefer a sender's own NodeInfo over the feeder's NodeDB view (the NodeDB truncates names and zeroes MACs). Also fix the latent int-versus-str comparison in `packets/services/node_info.py`.
6. **Carrying state across a link** (claims, watches, DX metadata, RF profile, inherited position, suppression of new-node baselines and DX logic) and linked history in the API and UI are later work built on the link signal, not part of this ADR's first steps.

**Implementation note (step 1):** the stored evidence, `common/meshtastic_identity.py` and the `backfill_meshtastic_identity` command have landed (api#439); see [meshtastic.md](../meshtastic.md#identity-evidence-and-predicted-28-node-id). Steps 2 to 6 remain planned.

## Consequences

- **Verification on hardware is pending.** Whether zlib `crc32(pubkey)` equals the firmware's `ErriezCRC32` result is inferred from source only. Nothing that acts on a prediction in production (auto re-key, auto links) is enabled until an upgrade of a spare node shows predicted and real numbers agree. Also unanswered: whether `my_info` is resent on a mid-session number change, whether Heltec 2.8.2 updates without an erase (keeping the key), and what a downgrade does to the number.
- Auto links are possible only for upgrades that keep the key. Full erases, licensed nodes and nodes whose key was never heard stay unlinked or suggested.
- Prediction is only as good as the stored key. Nodes never heard sending NodeInfo have none.
- Before link detection lands, an upgraded sender is a new "Unknown Node" and triggers a baseline traceroute and DX new-node checks; the old row will eventually look offline.
- A downgrade reverses the number change; the link logic must tolerate it (behaviour to be recorded from the hardware rollback test).
- Out of scope: server-side verification of XEdDSA signatures, and a canonical merged-node model (rejected in favour of two rows plus an alias).

## Evidence

- Firmware (v2.8.2): `NodeDB.cpp:543`, `4799-4859` (`generateCryptoKeyPair`), `4881-4917` (`createNewIdentity`), `4804-4811` (region unset), `Router.cpp:652-686` (first-contact check), `NodeDB.cpp:518`, `NodeInfoModule.cpp:187`, `TypeConversions.cpp:150-151`, `PhoneAPI.cpp:620-622` (`macaddr` handling).
- Meshflow code: `packets/services/base.py` (placeholder `ObservedNode` creation), `packets/services/node_info.py`, `packets/serializers.py` (`BaseNodeSerializer`), `nodes/models.py`, `mesh_monitoring/constants.py` (6 h offline).
- Hardware fixtures and the crc32 verdict will live under `docs/packets/meshtastic-2.8/` once captured; see the [upgrade runbook](../meshtastic-2.8-upgrade-runbook.md).
