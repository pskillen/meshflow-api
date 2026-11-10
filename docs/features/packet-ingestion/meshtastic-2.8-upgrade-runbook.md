# Meshtastic 2.8 feeder upgrade runbook

**Status:** Final · **Tracking:** [meshflow-api#437](https://github.com/pskillen/meshflow-api/issues/437)

Part of [packet ingestion](README.md). Design background: [ADR-0005 feeder-scoped auth](adr/0005-feeder-scoped-auth.md) and [ADR-0006 identity linking](adr/0006-meshtastic-identity-linking.md).

## Why a runbook

In Meshtastic 2.8 a node's number is `crc32(public key)`, so an upgraded feeder's number changes. A feeder that still posts under its old number on a legacy URL gets a 403 and stops ingesting without any visible error; that is why a v4-capable bot is a hard minimum below. A feeder on a v4 URL keeps ingesting (the API key identifies the feeder) and the API follows the number change. 2.8 also changes what the feeder radio passes to the bot (Traffic Management drops some packets before the bot, broadcast telemetry and public positions are switched off on upgrade, signing fields appear). The steps below keep ingest running and the node's history attached.

The identity behaviour below was observed on hardware on 2026-11-08 and 2026-11-09 (a Xiao nRF52840 and a Heltec Wireless Paper, both on 2.8.2) and in pre-prod on 2026-11-10 (a real automatic re-key of the Heltec feeder). 2.8.1 and 2.8.2 are both Alpha releases; the latest stable-track release is still 2.7.x. Decide separately whether a feeder should run an alpha.

## Hardware plan for the first runs

- The **production feeder stays on 2.7** until the gates below are met.
- The **pre-prod feeder is upgraded first** (to 2.8.2).
- A **spare radio** is upgraded as a 2.8 sender, to observe the sender-side identity change.
- 2.7 senders come from the live mesh. There is no second 2.8 sender, so 2.8 to 2.8 cases are only seen if a live-mesh 2.8 node happens to be heard.

## 1. Gates

Do not upgrade a feeder until all of these hold. Each is checkable.

- [ ] **API:** the target environment runs api **2.5.0 or later** for the re-key itself, and the release that carries the signing state, identity links and re-point audit (api **2.7.0**, not yet published at the time of writing; if it is still unpublished, take the release that includes them from the changelog). Migrations applied; `python manage.py backfill_meshtastic_identity` has been run (idempotent).
- [ ] **UI:** ui **2.4.0** or later, so My Nodes shows the "Feeder number changed" and "Feeder review" notices.
- [ ] **Bot:** bot **2.3.1** or later (not yet published at the time of writing; latest is 2.3.0), the release that holds the v4 URLs (bot#158), the connect-replay drop (bot#160) and the v4 probe before any upload (bot#166). **A feeder on bot 2.2.0 uses legacy URLs and cannot survive an upgrade.** Check the bot log after a restart:
  - `using v4 (feeder-scoped) feeder URLs` is logged before any upload;
  - the first API request after boot is `GET /api/v4/feeder/identity/`;
  - NodeDB uploads go to `POST /api/v4/feeder/meshtastic/nodes/` and return 200;
  - there is no 403 and no identity-rejection line.
- [ ] **Own key:** the feeder has **its own API key**, not shared with another feeder.
- [ ] **Stored public key:** the feeder's public key is visible on its `ManagedNode`, and was first recorded **more than an hour ago**. A key first recorded from a report is not trusted for the automatic re-key until it is an hour old (flagged `key_mismatch` until then).
- [ ] **Re-key flag decision:** decide whether `MESHTASTIC_FEEDER_AUTO_REKEY` is on for this environment (step 4). On is the tested path. Off means a person re-points each feeder.
- [ ] **Backup** of the radio config, private key included, stored offline (step 2).
- [ ] **Region** is set on the radio.
- [ ] **Board** is not an nRF52832.
- [ ] **Watchers warned:** people watching the feeder or its old number know a number change is coming (see Known limitations).
- [ ] **Soak:** the pre-prod feeder has run 2.8.2 for 7 days without ingest loss.

## 2. Pre-upgrade checklist

- [ ] Record the feeder's node id, public key, MAC and firmware version (the bot's identity report, or the CLI).
- [ ] Confirm in admin that the **predicted 2.8 id** for that key is shown on the node.
- [ ] **Back up the radio config offline, private key included.** Store it securely; never commit it. `--info`, `--export-config` and `--get security` output contain the private key and Wi-Fi and channel secrets.
- [ ] A **region is set** on the radio. A key (and so the new number) is only minted once a region is set.
- [ ] The board is **not an nRF52832** (that variant is dropped in 2.8; it stays on 2.7).
- [ ] Note the current bot version and API key label.

## 3. Flash

- Use the web flasher's **update** option with **full erase off**. **Never full-erase a feeder.** A full erase rotates the private key, so the node gets an unpredictable new number and cannot be linked to its history by key.
- Observed: the Heltec Wireless Paper (ESP32-S3) update path, 2.7.20 to 2.8.2, **kept the key, wifi and region**; the number went from `!433b82f0` to `!8959691b`, exactly as predicted from the stored key. The Xiao nRF52840 update also kept the key (`!1a83cf89` to `!e0a76739`).
- **The NodeDB is reset by the update.** The Heltec went from 200 nodes to 4. Expect the feeder's first NodeDB upload after the upgrade to be near-empty and the connect replay burst to be small. This is accepted; the NodeDB refills as the feeder hears the mesh.
- If an erase does happen, restore the private key from the offline backup **before the bot reconnects**.
- **Do not change the region or the key during or after the flash.** A key change sent over the client API reboots the radio within 2 seconds, so there is no mid-session number change. Clearing a key does not mint a new one; a new key must be set explicitly.

## 4. Re-key: what to set and what you will see

**Setting.** `MESHTASTIC_FEEDER_AUTO_REKEY` (see [ENV_VARS.md](../../ENV_VARS.md)) is `false` by default. Turn it on only when you accept that a `crc32(key)` match is the proof (confirmed on hardware, and exercised end to end in pre-prod). Turning it on applies a waiting change within 10 minutes.

**What the owner sees.**

| Flag | API | Owner |
| --- | --- | --- |
| On | The re-key is applied within 10 minutes of the feeder's report (the reported number is written at most every 10 minutes): `ManagedNode.meshtastic_node_id` moves, an `auto_updated` event is written, an identity link from the old row to the new one is recorded, and the owner's claim follows to the new `ObservedNode` when the stored key did not come from a report. | A Discord DM ("Your feeder ... changed node number: !old is now !new. It keeps its history and API key. Nothing to do.") and a "Feeder number changed" notice on My Nodes. If an earlier flagged event was never dismissed the owner also sees "Feeder review resolved" until both are dismissed. |
| Off | Flagged `auto_rekey_disabled`; the number is not changed. The feeder keeps ingesting with `identity_mismatch: true` until it is re-pointed. | A Discord DM (at most one flagged DM per feeder per 24 hours) and a My Nodes notice with a **Re-point** button that works when the proof holds. |

In pre-prod the open flagged event was resolved and the `auto_updated` event written 5 minutes 20 seconds after the API restart with the flag on. The Discord DM was recorded as sent by the server; its display in Discord and the rendered My Nodes page were not checked by eye.

**Flagged reasons and what to do.**

| Reason | Meaning | Operator action |
| --- | --- | --- |
| `auto_rekey_disabled` | The proof holds but the flag is off (or a manual reversal is holding). | Re-point by hand (below), or turn the flag on. |
| `key_not_reported` | The bot sent no public key. | Check the bot version and that the radio reports its key; the next report re-evaluates. |
| `crc_mismatch` | `crc32(key)` is not the reported number. On a 2.7 radio the number is MAC-based, so this usually means a config copied to another radio. | Do not re-point until the cause is understood. |
| `key_mismatch` | The key differs from the stored key, no key is stored, or the stored key was first recorded from a report **less than an hour ago** (the 1-hour settle). A later report re-evaluates, so a real feeder applies once the hour has passed. Also raised with the number unchanged when a 2.7 key regeneration changes the key but not the MAC-based number. | Wait an hour for the settle case. For an unchanged number with a new key, staff accept the reported key (`accept_reported_key` on the re-point endpoint). |
| `shared_key` | Another node holds the same key (a cloned key). **Never automatic**: a crc32 match on a cloned key proves nothing. | Re-point by hand after checking which radio is the feeder. |
| `number_collision` | The reported number is invalid, held by another active feeder, or claimed by someone else. | Staff resolve the collision first. |

**Re-pointing by hand.** The owner presses Re-point on My Nodes (or calls `POST /api/nodes/managed-nodes/{internal_id}/repoint-meshtastic-id/`); it works when the proof holds: the feeder reported that number and `crc32` of the trusted stored key gives it. Staff re-point in every other case (a new key, a number the key does not prove, or reversing a re-key). See [Managed nodes](../node-lifecycle/managed-nodes.md#re-pointing-a-feeder-by-hand). The feeder keeps its row, history and API key.

**A blank-key feeder that reaches v4 already upgraded stays flagged**, because there is no stored key to prove the change. Rescue it with `python manage.py backfill_meshtastic_identity` (fills blank keys only, then wait out the first-key hour) or have staff re-point it. The backfill's source is NodeDB data the client can write, so treat that key as a claim, not a proof.

**Rollback does not re-key.** A downgrade keeps the crc32 number, so the radio still reports the number the `ManagedNode` already has and nothing changes (step 8).

**Direct messages after a re-key.** A 2.8 peer cannot DM the new number until it learns the new key. The first DM fails with a NAK `PKI_SEND_FAIL_PUBLIC_KEY`; two direct NodeInfo exchanges and a reboot did not help, and it resolved by itself in about an hour (periodic NodeInfo). Allow for this in test traffic and when asking anyone to message the feeder.

## 5. Feeder radio settings after the upgrade

| Setting | Value | Why |
| --- | --- | --- |
| `security.packet_signature_policy` | `COMPATIBLE` (the default) | `STRICT` drops unsigned traffic, which includes every 2.7 sender; `BALANCED` refuses unsigned identity updates from known signers. COMPATIBLE senders send unsigned NodeInfo; one signed NodeInfo was captured from a BALANCED sender. The pre-prod feeder stayed COMPATIBLE. |
| Traffic Management `position_min_interval_secs` | `0` | Default position dedup (6 h, unmoved nodes on well-known channels) discards repeat positions **before the bot sees them**. `0` disables the dedup. Optional; leave the default if you accept fewer position observations from this feeder. **Not tested on our hardware.** |
| Public-channel position precision | Restore if wanted | The upgrade sets it to 0 and the public clamp is about 730 m (15 bits) |
| Telemetry | See step 6 | |

The API ignores the connect-time replay of stored node records a 2.8 radio sends after `config_complete_id`: replayed packets are stored and flagged but change nothing (see [meshtastic.md](meshtastic.md#replayed-packets-28)). Bots with replay detection (bot#160) drop them before upload.

Expect observation counts from a 2.8 feeder to differ from a 2.7 one even after these settings: pre-hop packets are withheld from the phone/bot, and broadcast hop limits are density-scaled.

## 6. Feeder telemetry

The upgrade turns off all **broadcast** telemetry. The radio still hands the connected bot the feeder's own device metrics about once a minute, and the bot throttles its upload to one per 15 minutes (`0` disables; there is no server-side throttle).

- **Default: rely on the bot's upload of the feeder's own telemetry.**
- **Optional: re-enable device telemetry broadcast** on the radio, per feeder. Other feeders then hear it and log it too, so it appears once from the feeder itself and again as an observation by neighbours.
- **Not separated:** whether the bot can tell the radio's local copy from its over-the-air broadcast. Broadcast telemetry stayed off in the hardware runs, so the two were never compared. Do not rely on the distinction.

## 7. Verify

After the bot reconnects:

- [ ] Ingest returns 200 under the feeder (bot log; admin shows new observations).
- [ ] The bot log shows `using v4 (feeder-scoped) feeder URLs`, the identity GET first, NodeDB posts to the v4 URL returning 200, and no 403.
- [ ] The feeder's `ManagedNode` shows the new node number, **or** a flagged identity-change event if auto re-key is off (then re-point after checking the key).
- [ ] The old number has an identity link to the new one and the owner was notified (DM and My Nodes notice).
- [ ] The feeder's own metrics are flowing.
- [ ] Mesh monitoring raised no offline alert for the feeder. Watchers of the old number may get one (Known limitations).

If ingest is not 200, check in this order: bot is on a v4 URL; key is the feeder's own (not `shared_api_key`); bot log for a number change; admin for a flagged event.

If the API is held by its fail-closed start guard (for example a migration is pending), it ingests nothing, and what the bot sends during the hold is lost, not queued. In the pre-prod run the bot logged connection errors for about five hours and those packets were not recovered. Release the guard before an upgrade day. The bot reconnects by itself within about 15 seconds of an API restart.

## 8. Rollback

Findings from the hardware session (2026-11-08, one Xiao, 2.8.2 to 2.7.26 and back):

- A 2.8.2 to 2.7.26 downgrade (app-only DFU, no erase) **kept the crc32 number and the key** on a re-keyed node (`!faec6f41`, the number predicted before the key was written), plus the owner, region and channels. The 2.7 radio keeps the stored number; it does not revert to the MAC-based number, so there is no second identity change. **The `ManagedNode` needs no change on rollback**: the radio still reports the crc32 number, so no re-key happens.
- A later 2.7 to 2.8 re-upgrade keeps the identity but **empties the NodeDB** (device state versions 24 and 25 differ), as does the ESP32 update in step 3. Expect the feeder to hear its mesh again from scratch and the 2.8 connect-time replay to be small until the NodeDB refills.
- 2.8.2 ignores the 1200-baud DFU touch on nRF52 (the USB CDC does not honour it). Run `meshtastic --enter-dfu` first, then flash.
- If the config was lost, restore the private key backup before the bot reconnects.

## 9. Known limitations

- **Until ID-3:** watches, DX metadata, claims on the old row and history stay on the old number. Watchers of the old node may get an offline alert once the learned threshold (6 to 48 hours) passes. Identity links are made at re-key time when deployed, or later by `python manage.py detect_meshtastic_identity_links` from key evidence; nothing yet carries state across a link.
- **NodeDB reset:** an ESP32 update resets the NodeDB (200 to 4 nodes observed), and an nRF52 re-upgrade empties it.
- **Not tested:** Traffic Management dedup behaviour, broadcast telemetry on or off, and a 2.7 feeder hearing a 2.8 sender. A signed NodeInfo was captured once from a BALANCED sender; the COMPATIBLE default sends unsigned.
- **DMs to a re-keyed node** fail for about an hour (step 4).

## 10. Fleet order

1. One **pre-prod feeder** first, then soak for 7 days.
2. One **low-traffic prod feeder**, then soak.
3. The rest, **one region at a time**, never two neighbouring feeders on the same day.

## Related

- [meshtastic.md](meshtastic.md): packet types and data path.
- [adr/](adr/README.md): ADR-0005, ADR-0006.
- [Managed nodes](../node-lifecycle/managed-nodes.md#node-number-changes-28): what the owner sees, and the re-point.
