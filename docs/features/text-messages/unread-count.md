# Text messages — unread count (WebSocket → UI)

**Purpose:** How new text messages reach the browser for realtime UI and unread badges. Unread state is **client-only** in meshflow-ui.

**UI counterpart:** [meshflow-ui `docs/features/messages/unread-count.md`](https://github.com/pskillen/meshflow-ui/blob/main/docs/features/messages/unread-count.md)

**Tracking:** [meshflow-ui#279](https://github.com/pskillen/meshflow-ui/issues/279). Deferred UI rollup: [meshflow-api#396](https://github.com/pskillen/meshflow-api/issues/396). Epic: [#341](https://github.com/pskillen/meshflow-api/issues/341).

---

## What the API does (and does not do)

| Responsibility | Owner |
| --- | --- |
| Persist `TextMessage` with correct `protocol` | `text_messages` + ingest |
| Broadcast new rows to UI clients | `ws` via Channels group `text_messages` |
| Unread / read receipts | **Not implemented** — SPA only |

---

## Code anchors

| Piece | Path |
| --- | --- |
| Model `protocol` | `Meshflow/text_messages/models.py` |
| REST serializer | `Meshflow/text_messages/serializers.py` |
| WS serializer | `Meshflow/ws/serializers.py` — `TextMessageWSSerializer` (includes `protocol`) |
| WS notify | `Meshflow/ws/services/text_message.py` |
| Tests | `Meshflow/ws/tests/test_text_message_ws_serializer.py` |

---

## WebSocket payload shape

`TextMessageWSSerializer` includes `protocol` (`meshtastic` / `meshcore`, same labels as REST). Also: `id`, `channel`, `sender`, `sent_at`, `message_text`, `is_emoji`, `reply_to_meshtastic_packet_id`, `original_packet_id`, `heard` (MT prefetch when available).

Still narrower than REST for MC helper fields (`mc_sender_label`, `mc_sender_candidates`).

OpenAPI documents WS frames as the `TextMessage` schema; `protocol` is required for correct UI classification ([#279](https://github.com/pskillen/meshflow-ui/issues/279)).

---

## Known gaps

- MC sender helper fields not on WS payload.
- `TextMessageConsumer` uses `print` when forwarding (log noise).
- UI dedupes by message `id`; API does not suppress duplicate pushes.

---

## Related

- [README.md](README.md)
- [meshflow-ui unread-count.md](https://github.com/pskillen/meshflow-ui/blob/main/docs/features/messages/unread-count.md)
- [#396](https://github.com/pskillen/meshflow-api/issues/396) — multi-constellation unread rollup (UI)
