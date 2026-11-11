# ADR-0006 — Meshtastic identity linking (2.7 to 2.8 node numbers)

**Status:** Accepted. Steps 1, 2, 4 and 5 are built; step 3 is operator guidance; linked history is shown both ways in the API (step 6, first part); carrying state across a link (watches, claims) is later work. The central assumption (zlib `crc32` equals the firmware's value) is **verified on hardware**.
**Date:** 2026-11-02 (accepted 2026-11-10)

## Context

In Meshtastic 2.8 a node's number is the CRC-32 of its 32-byte Curve25519 public key (firmware `NodeDB.cpp:543`, `createNewIdentity()`). Until 2.7 the number was usually derived from the MAC (`mac[2..5]`). Facts from the firmware source at `v2.8.2` (the number and key behaviour has since been confirmed on hardware, see Consequences):

- An upgrade **reuses the existing private key**, so the new number is **predictable from a public key we already store**.
- A key is minted only once a region is set; with the region unset the number stays MAC-based. A key minted mid-session changes the number without a reboot.
- A **full erase rotates the key** (and so the number). Known low-entropy keys, unclamped keys and licensed nodes (no key in 2.7) also get a new key.
- Over-the-air NodeInfo still carries `macaddr`. The feeder's NodeDB-to-client path zero-fills it for other nodes (only the local node keeps it).
- 2.8 receivers enforce `crc32(user.public_key) == from` on first-contact signed NodeInfo.

Consequence for Meshflow: after an upgrade the node appears as a **new** `ObservedNode`, the old one goes silent (and mesh monitoring would raise false offline alerts), and claims, watches, DX metadata and RF profile stay on the old row. History splits because `from_int` and `relay_node` are raw numbers. `ObservedNode.meshtastic_public_key` is stored in mixed formats (base64 and hex).

## Decision

1. **Predict ahead of the upgrade.** Normalise every stored key (base64 or hex to 64-char hex; anything not 32 bytes yields null, never an error) and store `crc32` of it as `meshtastic_key_node_id` (indexed) on `ObservedNode`, with the same on `ManagedNode.meshtastic_public_key`. An idempotent backfill reads `ObservedNode.meshtastic_public_key`, falling back to the latest `NodeInfoPacket.public_key` for that `from_int`, and reports keys shared by several nodes. Worked example under test: `!da545c78` is predicted to become `!4396524c`. The zlib crc32 equals the firmware's number, confirmed on hardware 2026-11-08.
2. **Best-effort linking of old and new identities, never merging. Built.** Both `ObservedNode` rows are kept; an `ObservedNodeIdentityLink(old_node, new_node, evidence, confidence, state, detail)` row is the alias. `from_int` is never rewritten, so rollback is deleting link rows. Evidence:
   - **Strong, automatic (`auto`):** the same public key K, `crc32(K)` equals the new number, and exactly one other Meshtastic node holds K.
   - **Keys are not unique, so a shared key is never linked.** One key has been seen on 17 or more unrelated rows (cloned or copied keys), and 2.8.2 did not re-key them. Any key held by more than one candidate is *unlinkable*: one `flagged` row names every holder and no link is made. A flagged row is not a link and has no old or new node.
   - **Medium, automatic, at first sight (`predicted_number`):** a new row with no stored key whose number is exactly the one a single other row's stored key predicts (`meshtastic_key_node_id`), when that key is held by that row alone. It is linked `auto` at the new number's first packet, shown publicly, and corrected later: the same key replaces it with `public_key` evidence, a different key demotes it to `suggested` (`key_differs`), a key that becomes shared retires it. Owner decision: link at first sight, before the key is heard, because key evidence can take hours to arrive.
   - **Medium, suggested and needing confirmation (`suggested`):** the on-air `macaddr` M satisfies `int(M[2:6]) == old number` (or the MAC equals another row's stored `mac_addr`) and the other row's key differs. This covers full erases and licensed nodes. Only on-air NodeInfo counts: NodeDB uploads zero other nodes' MACs. Two candidates record nothing.
   - **Weak, hint only (not built):** names, hardware model, location.
   - States: `auto`, `suggested`, `confirmed`, `rejected`, `flagged`. A state only moves up (suggested, auto, confirmed); a `rejected` row is never recreated or promoted; the reverse of an existing pair is never created; a database constraint allows at most one live (`auto` or `confirmed`) successor per old row and one live predecessor per new row, and a violation is logged while ingest carries on. Staff confirm or reject in the Django admin until a staff API exists.
3. **A full erase is a new identity.** It rotates the key, so there is no key-based link and no prediction. Only the MAC signal can propose a link, and it needs confirmation. The upgrade runbook therefore says **never full-erase a feeder**.
4. **Managed feeders** are handled by [ADR-0005](0005-feeder-scoped-auth.md): the `ManagedNode` row is re-pointed (so observer foreign keys stay intact), and a `ManagedNodeIdentityEvent` is the audit alias. When that happens the `ObservedNode` link is created with evidence `feeder_rekey` (`auto` for an automatic re-key, `confirmed` for a manual re-point), merged into the key link when there already is one. **Built:** a receiver on `feeder_identity_changed` that never raises.
5. **Do not clobber identity.** NodeInfo ingest must ignore a blank or zero MAC, never replace a name with its own 24-byte prefix, never clear a stored key, and prefer a sender's own NodeInfo over the feeder's NodeDB view (the NodeDB truncates names and zeroes MACs). The int-versus-str "packet is about another node" guard in `packets/services/node_info.py` never matched and is removed.
6. **Linked history is shown both ways, never merged. Built (API).** A node's detail lists its other identities (`identity_chain`, `replaced_by`) and lists flag a replaced row; history stays on the row that recorded it. That is the owner's decision; a "move history" action is a possible later request. **Carrying state across a link** (claims, watches, DX metadata, RF profile, inherited position, suppression of new-node baselines and DX logic) is later work built on the link signal.

**Implementation notes:** step 1 (stored evidence, `common/meshtastic_identity.py`, the `backfill_meshtastic_identity` command) and steps 2 and 4 (`nodes/services/identity_links.py`, the `detect_meshtastic_identity_links` command, a signal when a link becomes live) are built, and step 6 shows linked identities in the API (`nodes/services/identity_chain.py`); see [meshtastic.md](../meshtastic.md#identity-evidence-and-predicted-28-node-id) and [Identity links](../meshtastic.md#identity-links). The first-packet link by predicted number and the `--predicted` backfill pass are built too. Carrying state across a link remains planned.

## Consequences

- **Hardware gate met (2026-11-08, verified on three radios).** zlib `crc32(pubkey)` equals the firmware's node number: an update keeps the key and takes the number predicted from it, a re-key takes the number predicted from the new key, and a **downgrade keeps both the number and the key**, so a downgrade makes no new row and needs no link. Still open: whether `my_info` is resent on a mid-session number change.
- Auto links are possible only for upgrades that keep the key. Full erases, licensed nodes and nodes whose key was never heard stay unlinked or suggested.
- Prediction is only as good as the stored key. Nodes never heard sending NodeInfo have none.
- Until state is carried across a link (step 6), an upgraded sender is still a new "Unknown Node" and triggers a baseline traceroute and DX new-node checks, and the old row will eventually look offline; the link row only records that they are the same radio.
- A downgrade keeps the number and the key, so the same row simply sends a new NodeInfo. The link logic does nothing in that case.
- Cloned keys are common, so key evidence is only trusted when the key has exactly one other holder; everything else is flagged for a person.
- Out of scope: server-side verification of XEdDSA signatures, and a canonical merged-node model (rejected in favour of two rows plus an alias).

## Evidence

- Firmware (v2.8.2): `NodeDB.cpp:543`, `4799-4859` (`generateCryptoKeyPair`), `4881-4917` (`createNewIdentity`), `4804-4811` (region unset), `Router.cpp:652-686` (first-contact check), `NodeDB.cpp:518`, `NodeInfoModule.cpp:187`, `TypeConversions.cpp:150-151`, `PhoneAPI.cpp:620-622` (`macaddr` handling).
- Meshflow code: `packets/services/base.py` (placeholder `ObservedNode` creation), `packets/services/node_info.py`, `packets/serializers.py` (`BaseNodeSerializer`), `nodes/models.py`, `mesh_monitoring/constants.py` (6 h offline).
- Hardware fixtures and the crc32 verdict will live under `docs/packets/meshtastic-2.8/` once captured; see the [upgrade runbook](../meshtastic-2.8-upgrade-runbook.md).
