# MeshCore channel message sender inference

MeshCore **channel** (`channel_message`) text on the wire carries **no sender pubkey** — only `channel_idx` and the message body ([ADR-0001 (node identity)](../packet-ingestion/adr/0001-mc-node-identity.md), [text-message-channels.md](text-message-channels.md)).

`TextMessage.sender` stays `null` for channel text. **Contact/DM** (`contact_message`) still sets `sender` from `from_pubkey_prefix` at ingest.

## On-air text convention

Many clients prefix channel messages as:

```text
{sender_name}: {message body}
```

Rules used by the API:

- Delimiter is **colon + single space** (`": "`). `Alice:hi` does not parse.
- The name is everything before the first `": "`.
- Empty name or empty body after the delimiter → no label (no candidates).

Example: `WMF: hello mesh` → label `WMF`.

This is **heuristic**, not a MeshCore protocol field. Wrong prefixes or edited bodies produce no match or wrong matches.

## API: `mc_sender_label` and `mc_sender_candidates`

On `GET /api/messages/text/` for MeshCore channel rows (`sender` null):

| Field | Meaning |
| --- | --- |
| `mc_sender_label` | Parsed name from `message_text`, or `null` |
| `mc_sender_candidates` | `ObservedNode` rows where `long_name` or `short_name` equals the label (case-insensitive). Often one node; duplicate display names return multiple. |
| `sender_position` | Position from `sender` when set; else position of the **only** candidate with known coordinates |

Each candidate includes: `internal_id`, `node_id_str`, `long_name`, `short_name`, `position` (from `NodeLatestStatus` when set, else the latest `Position` row — same rule as the node detail `latest_position` field).

Implementation: `text_messages/mc_channel_sender.py`; list responses bulk-load candidates per page.

## UI (heard map)

The message heard map uses `sender_position` when unambiguous. For MC channel text, the UI reads `mc_sender_candidates` and places the sender marker when exactly one candidate has `position`. Multiple matches: list still works; map may omit sender until the user disambiguates (future).

## Limitations

- No constellation filter on candidates today (global name match on all MC `ObservedNode` rows).
- Does not parse other prefix styles (`[Alice]`, etc.).
- Does not set `TextMessage.sender` FK (display-only inference).

**Related:** [meshcore-path-progress.md](../traceroute/meshcore-path-progress.md) (passive path / heard map).
