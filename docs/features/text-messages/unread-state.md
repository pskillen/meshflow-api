# Text messages: server-side unread state

**Tracking:** [#517](https://github.com/pskillen/meshflow-api/issues/517); UI consumer [meshflow-ui#422](https://github.com/pskillen/meshflow-ui/issues/422). Supersedes the server-side part of [#396](https://github.com/pskillen/meshflow-api/issues/396).

Unread badges survive reloads and count messages that arrived while the user was away, split by protocol.

## Model

`text_messages.MessageChannelReadState(user, channel, last_read_at)`, unique on `(user, channel)`. A message is unread for a user when `sent_at > last_read_at` for that channel. Channels are protocol-specific rows, so protocol comes from the channel.

## What counts

- Only **channel messages**, using the same filter as `GET /api/messages/text/` (Meshtastic broadcast; MeshCore channel messages with no resolved sender). Direct messages are not counted.
- **Visibility:** the list endpoint applies no per-user scoping (any channel is readable), so every channel is visible to any authenticated user. Both new endpoints go through one `visible_channels()` helper, so tightening scoping later is a one-line change.
- **Bounds:** per channel, only messages from the **last 7 days** count, and each channel count is **capped at 99** (the UI shows "99+"). Totals are the sum of the capped channel counts.
- **No cursor yet:** the first `unread-counts` call creates a cursor at *now* for every visible channel lacking one, so nobody starts with a backlog. That call reports 0 for those channels.

## `GET /api/messages/unread-counts/`

Authenticated. Response:

```json
{
  "meshtastic": {"total": 12, "channels": {"3": 10, "5": 2}},
  "meshcore": {"total": 0, "channels": {}}
}
```

Both protocol keys are always present. `channels` lists only channels with at least one unread message, keyed by channel id. Fixed query count (channel list, cursor list, optional bulk cursor insert, one grouped count), independent of channel count.

## `POST /api/messages/channels/{id}/mark-read/`

Authenticated. Optional JSON body `{"up_to": "<ISO-8601 timestamp or message UUID>"}`; default is now. A message id must belong to that channel. Future timestamps are clamped to now. The cursor **never moves backwards**: an older `up_to` is a no-op (still 200). Response: `{"channel_id": 3, "last_read_at": "..."}`.

Errors: 400 for an unparseable `up_to` or a message id not in the channel; 404 for an unknown channel (or one the user cannot see).
