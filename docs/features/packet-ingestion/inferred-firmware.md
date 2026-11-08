# Inferred firmware generation

**Status:** shipped for Meshtastic (key-derived evidence only). MeshCore nodes are always unknown.

Each Meshtastic `ObservedNode` carries the firmware generation we can infer for it, or nothing when there is no evidence. Nothing is assumed: a node we know nothing about is *unknown*, not "2.7".

## Why it works

Meshtastic 2.8 sets a node's number to `crc32(public key)` (see [meshtastic.md](meshtastic.md#identity-evidence-and-predicted-28-node-id)). We store both the number and the key, so a node's number either matches its key or it does not.

## Evidence

| Evidence | `inferred_firmware` | `inferred_firmware_basis` |
| --- | --- | --- |
| Key known, number equals `crc32(key)` | `2.8` | `key_identity` |
| Key known, number differs | `2.7` | `key_identity` |
| Row has no key, its number is another row's `meshtastic_key_node_id` | `2.8` | `predicted_id` |
| No key known | null | null |

- **A missing key is not evidence of any version.** Some nodes predate PKI, or we have not heard the key yet. That includes an on-air NODEINFO that carries no key.
- **Unknown means unknown.** There is no `assumed` basis and no default value. The API returns null for both fields.
- **The value is a floor, not an exact version.** `2.8` means a 2.8 identity was seen. `2.7` means 2.7 or earlier, because 2.7 cannot be told from older releases.
- `predicted_id` covers a node that was re-numbered by an upgrade: the new row has no key yet, but its number is the key-derived id of the old row.
- A verdict is never cleared. A later keyless NODEINFO, or a malformed key, leaves the stored value alone.

### Known limit

A node downgraded from 2.8 keeps its key-derived number, so it keeps reading `2.8`.

## Code anchors

| What | Where |
| --- | --- |
| Rules, `classify`, `generation_for_version`, `ADOPTION_WINDOW_HOURS` (168, the one definition of "active") | `common/meshtastic_firmware.py` (pure, no ORM) |
| Applying a verdict to a row, refreshing keyless rows after a key write | `nodes/services/node_firmware.py` |
| Fields | `ObservedNode.inferred_firmware` (indexed, open set, no `choices`), `inferred_firmware_basis`, `inferred_firmware_at` (when the value last changed; not in the API) |
| Written by | `NodeInfoPacketService`, the node upsert serializer (`BaseNodeSerializer.create/update`), and `get_or_create_meshtastic_observed_node` for a brand-new keyless row |
| API | Read-only `inferred_firmware` and `inferred_firmware_basis` on the observed node (`openapi.yaml`) |

Both columns are nullable on purpose: a `NOT NULL` column would make an older image fail on insert, and no evidence reads `null` in the API rather than an empty string.

### Order independence

Evidence can arrive in any order. After a key is written, `refresh_row_numbered_by_key` re-evaluates any keyless row whose number is that key's derived id, so a new 2.8 row created before its old row's key arrives still ends `predicted_id`. Replays never move a classified row, and `inferred_firmware_at` changes only when the generation or basis changes.

## Adding a generation

1. Add a rule to `RULES` in `common/meshtastic_firmware.py` (the list is ordered, first verdict wins, so stronger evidence goes first).
2. Add the floor to `GENERATION_FLOORS`.

No migration and no serializer change: the field is an open string.

## Backfill

`python manage.py backfill_inferred_firmware [--dry-run] [--batch-size N]` classifies existing rows. It is idempotent (a second run updates nothing and leaves `inferred_firmware_at` alone), keyset-batched by primary key, and `--dry-run` writes nothing and reports what a real run would write.

It prints a scan summary, a count per result, and the key coverage of recently active nodes (heard within `ADOPTION_WINDOW_HOURS`), which says how much of the active mesh can be classified at all:

```
ObservedNode: scanned N, updated N
By result: 2.7/key_identity N, 2.8/key_identity N, 2.8/predicted_id N, unknown N
Active in the last 168h: N, with a usable key N (P%)
```

It reads the stored `meshtastic_key_node_id`. In an environment that never ran it, run `backfill_meshtastic_identity` first.
