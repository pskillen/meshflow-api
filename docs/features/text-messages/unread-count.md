# Text messages — unread count (WebSocket → UI)

**Purpose:** Document how new text messages reach the browser and why sidebar unread badges can mix Meshtastic (MT) and MeshCore (MC) counts. Unread is **not** computed or stored in meshflow-api; the API only **pushes** message JSON. Scoping logic lives in meshflow-ui.

**UI counterpart:** [meshflow-ui `docs/features/messages/unread-count.md`](https://github.com/pskillen/meshflow-ui/blob/main/docs/features/messages/unread-count.md)

**Tracking:** [meshflow-ui#279](https://github.com/pskillen/meshflow-ui/issues/279) (bug). Parent epic: [meshflow-api#341](https://github.com/pskillen/meshflow-api/issues/341).

---

## What the API does (and does not do)

| Responsibility | Owner |
| --- | --- |
| Persist `TextMessage` with correct `protocol` | `text_messages` + ingest services |
| Broadcast new rows to logged-in UI clients | `ws` app via Channels |
| Per-user unread state, read receipts, badge counts | **Not implemented** — SPA only |

There is no `GET /api/messages/unread/` and no DB column for “read”. Clearing unread in the UI does not call the API.

---

## Code anchors

| Piece | Path |
| --- | --- |
| Model `protocol` field | `Meshflow/text_messages/models.py` |
| REST serializer (includes `protocol`) | `Meshflow/text_messages/serializers.py` — `TextMessageSerializer.get_protocol` → `"meshtastic"` / `"meshcore"` |
| WS serializer (**no `protocol`**) | `Meshflow/ws/serializers.py` — `TextMessageWSSerializer` |
| WS notify | `Meshflow/ws/services/text_message.py` — `TextMessageWebSocketNotifier.notify` |
| Signal → WS | `Meshflow/ws/receivers.py` — `@receiver(text_message_received)` |
| Consumer | `Meshflow/ws/consumers.py` — `TextMessageConsumer` |
| Routing | `Meshflow/Meshflow/routing.py` — `ws/messages/` |
| Signal definition | `Meshflow/packets/signals.py` — `text_message_received` |
| MT row creation | `Meshflow/packets/services/text_message.py` |
| MC row creation | `Meshflow/meshcore_packets/services/text_message.py` |

---

## Emit path

Both protocols call the same signal after insert:

1. Ingest creates `TextMessage` with `protocol=Protocol.MESHTASTIC` or `Protocol.MESHCORE`.
2. `text_message_received.send(sender=..., message=message, observer=...)`.
3. `TextMessageWebSocketNotifier` serializes and `group_send`s to Redis group **`text_messages`**.
4. Every connected `TextMessageConsumer` receives `text_message` and `send(text_data=json.dumps(event["message"]))`.

All authenticated UI sessions share one broadcast group (no per-user or per-protocol channel split).

---

## WebSocket payload shape

`TextMessageWSSerializer` fields today:

| Field | In WS payload | In REST `TextMessageSerializer` |
| --- | --- | --- |
| `id` | Yes | Yes |
| `protocol` | **No** | Yes (`meshtastic` / `meshcore`) |
| `original_packet_id` | Yes (MT) | Yes (+ `original_mc_packet_id` on REST) |
| `sender` | Yes (brief) | Yes |
| `channel` | Yes (PK) | Yes |
| `sent_at`, `message_text`, `is_emoji`, `reply_to_meshtastic_packet_id` | Yes | Yes |
| `heard` | Yes (prefetched MT observations) | Yes (MT + MC paths) |
| `mc_sender_label`, `mc_sender_candidates` | **No** | Yes (MC) |

OpenAPI states WS frames use the same schema as `TextMessage`; **implementation is narrower than REST** for realtime pushes.

---

## Why this breaks protocol-scoped unread ([#279](https://github.com/pskillen/meshflow-ui/issues/279))

meshflow-ui classifies each WS frame with `messageProtocol(msg)` (`src/lib/message-protocol.ts`):

- Explicit `msg.protocol === 'meshcore'` (or legacy `2` / `'mc'`) → MeshCore.
- **Otherwise → Meshtastic.**

When `protocol` is absent from the JSON (all WS pushes today), **every** message is treated as Meshtastic for:

- `unreadCountForProtocol('meshtastic')` / `hasUnreadForProtocol('meshtastic')`
- `markAsReadForProtocol('meshcore')` (MC rows never removed from unread list)
- `useMessagesWithWebSocket` protocol filter (MC realtime on messages page may not prepend)

Nav code in `nav-main.tsx` already calls `unreadCountForProtocol(messagesProtocol)` per link; the bug is **misclassification of payload**, not use of global `unreadMessages.length` on badges.

### Intended fix (API side)

Add `protocol` to `TextMessageWSSerializer` (same string labels as REST), and align OpenAPI / any WS tests. Optional: include `original_mc_packet_id` or `packet_id` for parity with list responses.

### UI-side hardening (optional)

Infer MC only when REST fields exist, or fetch protocol after WS receive — fragile compared to fixing the serializer.

---

## Infrastructure

| Concern | Detail |
| --- | --- |
| Redis | Channels layer; group name `text_messages` — [REDIS.md](../../REDIS.md) |
| Auth | JWT query param `token` on connect (`TextMessageConsumer`) |
| Separate from feeder WS | `/ws/nodes/` is bot commands only — [meshcore/phase-2-outstanding.md](../meshcore/phase-2-outstanding.md) |

---

## Known gaps

- WS payload missing `protocol` (primary cause of [#279](https://github.com/pskillen/meshflow-ui/issues/279)).
- WS payload missing MC sender helper fields (affects display if UI ever rendered unread toasts from WS-only data without REST merge).
- `TextMessageConsumer` still uses `print` when forwarding (noise in logs).
- No deduplication if the same message were pushed twice (UI appends blindly).

---

## Related

- [README.md](README.md) — text messages hub
- [../meshcore/text-message-channels.md](../meshcore/text-message-channels.md) — MC ingest
- [meshflow-ui unread-count.md](https://github.com/pskillen/meshflow-ui/blob/main/docs/features/messages/unread-count.md) — client state, nav, mark-as-read
