# Meshtastic 2.7/2.8 capture goldens

The API side of the labelled capture subset the bot keeps under `docs/meshtastic_packets/2.8` (`subset.json`, 36
entries, by `key`). One physical radio (NIAV-1) was captured across an upgrade and a re-key, as three feeders:

| Capture | Feeder number | Firmware |
| --- | --- | --- |
| `x27` | `!1a83cf89` (444845961) | 2.7.26 |
| `x28`, `x28h4` | `!e0a76739` (3769067321) | 2.8.2 |
| `x28f` | `!faec6f41` (4209798977) | 2.8.2, after the re-key |

## Layout

| Path | What |
| --- | --- |
| `manifest.json` | One entry per key: `key`, `labels`, `kind`, `feeder_num`, `bot_ref` (the bot commit the wire came from) |
| `wire/<key>.json` | The ingest body the bot sends for that entry (default mode) |
| `wire/<key>+flag.json` | Flag-mode body (`{**packet, "replayed": true}`), for the 7 replay keys only |
| `golden/<key>.json` | Expected API outcome, one per wire file |

`x27-L37` is an encrypted packet the bot never sends; its wire file is here so the API's 304 is held too.

## Where the inputs come from

`wire/` is generated, not hand-written. `Meshflow/packets/tests/gen_meshtastic_wire.py --bot <meshflow-bot checkout>`
loads the bot's `subset.json` through the bot's `tools/meshtastic_fixtures/load.py` and runs each packet through the
bot's `MeshtasticPacketSerializer.serialise_raw_packet` with `time.time` patched to the entry's `t_host`, so the
`rxTime` fallback is reproducible. Run it by hand, not in CI; the bot commit is recorded in `manifest.json`. To use the pinned bot, check it out at `.github/contract/bot-ref` (recipe in `tests/TESTING.md`, "Bot contract test").

## The golden format

```json
{
  "key": "x28-L4",
  "request": {"url": "v4", "feeder_num_header": 3769067321},
  "status": 201,
  "packet": {"model": "PositionPacket", "fields": {"...": "every non-volatile model field"}},
  "observation": {"hop_start": 3, "hop_limit": 3, "bitfield": null, "rx_time": "<ISO>", "replayed": true, "channel": 0},
  "observed_node": null,
  "effects": {"observed_node_created": false, "last_heard_advanced": false, "position_rows": 0, "nls": {},
              "dx_candidate_called": false, "baseline_traceroute_queued": false,
              "observation_api": {"replayed": true, "hop_count": null, "direct_from_sender": false}}
}
```

- Setup per test: a fresh database, one `ManagedNode` registered with `0x1a83cf89` (the pre-upgrade number, as in
  production) on a single-feeder key. The wire body is POSTed to v4 with `X-Meshtastic-Feeder-Node-Num` set to the
  entry's `feeder_num`. One parity test posts `x27-L7` to the v3 URL and expects the same golden.
- Volatile values never appear: `upload_time`, `first_reported_time`, `last_heard`, ids, UUIDs, and the `*_at` /
  `*_reported_time` stamps. Effects are booleans and counts measured against a snapshot taken before the POST.
- `nls` holds the sender's `NodeLatestStatus` fields that changed. `observed_node` is the sender's row (non-time
  fields), null when none was created. A 304 golden has `packet: null`.
- The DX-detection and new-node-baseline entry points are patched where they are looked up; the sender is a new node,
  so the baseline is queued for every live packet. Self goldens (`kind:self`) use a bare `ManagedNode` setup, so the feeder's own packet creates its `ObservedNode` and the new-node, DX and baseline effects fire; in production that node already exists.

## Regenerating

```bash
cd Meshflow
MESHFLOW_REGEN_GOLDENS=1 pytest --no-cov -q --create-db packets/tests/test_meshtastic_goldens.py
git diff docs/packets/meshtastic-2.8   # read every change; nothing should move unless behaviour did
```

Regenerating on unchanged code changes nothing.

## Contract job

The `contract` CI job (`.github/workflows/contract.yaml`, test in `Meshflow/packets/tests/contract/`) replays the bot's
capture subset through the bot's serialiser and this API's ingest and compares with these `wire/` and `golden/` files,
so a break fails CI in whichever repo caused it. The API pins the bot ref it is tested against in
`.github/contract/bot-ref`; once the bot's PR job lands (not merged yet) the bot's PRs will run against API `main`. Changing a wire body or golden here means bumping the
pin in the same PR. See `tests/TESTING.md` ("Bot contract test").

## Label meanings

Labels come from the bot's subset (`labels` in `manifest.json`):

| Label | Meaning |
| --- | --- |
| `kind:live` / `kind:replay` / `kind:self` | Heard on air / 2.8 connect-time replay / the feeder's own packet |
| `port:<APP>`, `variant:<x>` | Portnum, and the telemetry variant |
| `sender-id:mac` / `crc32` / `unknown` | How the sender's number was derived: from its MAC (2.7), from the crc32 of its key (2.8), or unknown (no user record, or only a zeroed MAC) |
| `from-id-null` | `fromId` is present and null (known gap: the API stores `from_str` null instead of deriving it from `from`) |
| `hops-exhausted` | live packets only: `hopLimit` absent, proto3 drops zero, so the real value is 0, yet the API records `hop_limit` null (known gap: hop count unknown). On replays the absent `hopLimit` is firmware-fabricated, not an exhausted packet |
| `fake-direct` | A replay whose hop fields look direct (`hopStart == hopLimit`); the API reports no hop count and not direct |
| `stable-replay-id` | A replay keeps the same packet id across reconnects |
| `no-rx-time` | The capture has no `rxTime`; the bot fills it from its clock, so the API sees one |
| `bitfield:N` | `decoded.bitfield` value, stored on the observation when present |
| `channel:N` | Channel index when not 0 |
| `feeder:2.7` / `feeder:2.8` | Firmware of the capturing feeder |
