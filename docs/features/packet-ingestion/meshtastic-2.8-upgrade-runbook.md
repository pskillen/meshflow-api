# Meshtastic 2.8 feeder upgrade runbook

> **DRAFT. Do not follow this to upgrade a production feeder yet.** It describes **planned** behaviour: most of the API and bot support it relies on is not built or deployed. Nothing here has been run on hardware.
>
> **Pending before this is final:**
>
> - Results of the hardware session (identity snapshots, whether `crc32(public key)` equals the node number, mid-session key mint, 403 behaviour, signing and Traffic Management captures).
> - Rollback findings (what a 2.8 to 2.7 downgrade does to the node number and config). Step 7 is a placeholder until then.
> - Whether the Heltec 2.8.2 update keeps the key without an erase.
> - Bot version numbers: every "bot version TBD" below is a placeholder.
> - Whether the bot can tell a feeder's local telemetry from its broadcast telemetry (open question; see step 5).

**Status:** Planned · **Tracking:** [meshflow-api#437](https://github.com/pskillen/meshflow-api/issues/437)

Part of [packet ingestion](README.md). Design background: [ADR-0005 feeder-scoped auth](adr/0005-feeder-scoped-auth.md) and [ADR-0006 identity linking](adr/0006-meshtastic-identity-linking.md).

## Why a runbook

In Meshtastic 2.8 a node's number is `crc32(public key)`, so an upgraded feeder's number changes. A feeder that still posts under its old number on a legacy URL gets a 403 and stops ingesting without any visible error. 2.8 also changes what the feeder radio passes to the bot (Traffic Management drops some packets before the bot, broadcast telemetry and public positions are switched off on upgrade, signing fields appear). The steps below keep ingest running and the node's history attached.

The firmware facts come from the 2.8.2 source and release notes; they have not been exercised on our hardware yet. 2.8.1 and 2.8.2 are both Alpha releases; the latest stable-track release is still 2.7.x. Decide separately whether a feeder should run an alpha.

## Hardware plan for the first runs

- The **production feeder stays on 2.7** until the gates below are met.
- The **pre-prod feeder is upgraded first** (to 2.8.2).
- A **spare radio** is upgraded as a 2.8 sender, to observe the sender-side identity change.
- 2.7 senders come from the live mesh. There is no second 2.8 sender, so 2.8 to 2.8 cases are only seen if a live-mesh 2.8 node happens to be heard.

## 1. Gates

Do not upgrade a feeder until all of these hold. Bot version numbers are TBD.

| Gate | Needed |
| --- | --- |
| API | Feeder-scoped v4 URLs ([ADR-0005](adr/0005-feeder-scoped-auth.md)), predicted node ids and key backfill, no-clobber identity fix, and feeder re-key deployed to the target environment; the backfill has been run |
| Re-key switch | `MESHTASTIC_FEEDER_AUTO_REKEY` is on only if the crc32 match was confirmed on hardware; otherwise plan on a manual re-point |
| Bot | Version TBD or later: reports identity (key, MAC, firmware, node number) and detects a number change; probes v4 URLs and falls back; uploads throttled self telemetry; library pinned below 2.8 |
| Key | The feeder has **its own API key** (not shared with another feeder) |
| Identity | The feeder's public key is already visible on its `ManagedNode` |
| Docs | This runbook is no longer marked DRAFT and includes the rollback findings |

A feeder on a **legacy URL cannot survive the upgrade**. Confirm the bot is on a v4 URL (bot log, or the feeder's API generation in admin) before flashing.

## 2. Pre-upgrade checklist

- [ ] Record the feeder's node id, public key, MAC and firmware version (the bot's identity report, or the CLI).
- [ ] Confirm in admin that the **predicted 2.8 id** for that key is shown on the node.
- [ ] **Back up the radio config offline, private key included.** Store it securely; never commit it. `--info`, `--export-config` and `--get security` output contain the private key and Wi-Fi and channel secrets.
- [ ] A **region is set** on the radio. A key (and so the new number) is only minted once a region is set.
- [ ] The board is **not an nRF52832** (that variant is dropped in 2.8; it stays on 2.7).
- [ ] Note the current bot version and API key label.

## 3. Flash

- Use the web flasher's **update** option. **Never full-erase a feeder.** A full erase rotates the private key, so the node gets an unpredictable new number and cannot be linked to its history by key.
- If an erase does happen, restore the private key from the offline backup **before the bot reconnects**.
- Do not change the region during or just after the flash; a key minted later changes the number without a reboot.
- Open question: whether the Heltec 2.8.2 update keeps the key without an erase. This is checked in the hardware session.

## 4. Feeder radio settings after the upgrade

| Setting | Value | Why |
| --- | --- | --- |
| `security.packet_signature_policy` | `COMPATIBLE` (the default) | `STRICT` drops unsigned traffic, which includes every 2.7 sender; `BALANCED` refuses unsigned identity updates from known signers |
| Traffic Management `position_min_interval_secs` | `0` | Default position dedup (6 h, unmoved nodes on well-known channels) discards repeat positions **before the bot sees them**. `0` disables the dedup. Optional; leave the default if you accept fewer position observations from this feeder |
| Public-channel position precision | Restore if wanted | The upgrade sets it to 0 and the public clamp is about 730 m (15 bits) |
| Telemetry | See step 5 | |

Expect observation counts from a 2.8 feeder to differ from a 2.7 one even after these settings: pre-hop packets are withheld from the phone/bot, and broadcast hop limits are density-scaled.

## 5. Feeder telemetry

The upgrade turns off all **broadcast** telemetry, but the radio still sends the feeder's own device metrics to the connected bot. The bot has historically skipped telemetry sent by the feeder to itself. The plan:

- **Default: rely on bot-side upload of the feeder's own telemetry.** The bot uploads the latest sample of each telemetry variant for packets whose `from` is the feeder's own node number, throttled bot-side (default about every 15 minutes; `0` disables). There is no server-side throttle.
- **Optional: re-enable device telemetry broadcast** on the radio. This is the owner's choice per feeder. When a feeder broadcasts, **other feeders hear it and log it too**, so it appears once from the feeder itself and again as an observation by neighbours.
- **Open question:** whether the bot can distinguish the radio's local copy from its over-the-air broadcast (both arrive `from` the feeder's own number). Hardware captures with broadcast off and on are needed. Until then, do not rely on the distinction.

## 6. Verify

After the bot reconnects:

- [ ] Ingest returns 200 under the feeder (bot log; admin shows new observations).
- [ ] The feeder's `ManagedNode` shows the new node number, **or** a flagged identity-change event if auto re-key is off (then re-point manually after checking the key).
- [ ] The old number is kept as an alias and the owner was notified.
- [ ] The feeder's own metrics are flowing.
- [ ] Mesh monitoring raised no offline alert for the feeder or for its linked old node.

If ingest is not 200, check in this order: bot is on a v4 URL; key is the feeder's own (not `shared_api_key`); bot log for a number change; admin for a flagged event.

## 7. Rollback

**TBD: pending the hardware rollback test.** Findings needed: after a 2.8 to 2.7 downgrade without an erase, does the node number revert to the MAC-based id, stay as the crc32 id, or does the config reset? What the API does on a reversion (the link logic must tolerate it) follows from that. Until it is recorded: restore the private key backup if the config was lost, and do not downgrade a production feeder.

## 8. Fleet order

1. One **pre-prod feeder** first, then soak for 7 days.
2. One **low-traffic prod feeder**, then soak.
3. The rest, **one region at a time**, never two neighbouring feeders on the same day.

## Related

- [meshtastic.md](meshtastic.md): packet types and data path.
- [adr/](adr/README.md): ADR-0005, ADR-0006.
