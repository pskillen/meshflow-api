# Discord notifications (bot DMs)

How Meshflow sends **direct messages** via a Discord **bot**, and how the HTTP API exposes prefs + a test message. This is **not** the social-login flow; for OAuth/JWT see [`docs/AUTH.md`](../../AUTH.md). For linking Discord to an existing account vs logging in with Discord, see [Account linking](account-linking.md).

## Implementation boundary

| Layer | Location |
|-------|----------|
| Bot DM transport (`DISCORD_BOT_TOKEN`, Discord REST) | **`push_notifications`** — `push_notifications.discord` |
| OAuth, account link, `SocialAccount`, `discord_notify_*` sync | **`users`** — `discord_sync`, signals, login/connect views |
| Prefs + test HTTP routes (`/api/auth/discord/notifications/…`) | **`users`** — `views_discord` (uses `push_notifications.discord` to send) |

**Discord OAuth** (`DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET`) powers “Login with Discord” and **linking** (`/api/auth/social/discord/connect/`). That is separate from the **bot token** used to open DM channels and send messages.

## Verify ownership (anti-spam)

The API only sends DMs (including the **test** endpoint) when:

1. The user has linked Discord via OAuth (django-allauth `SocialAccount` with `provider=discord`).
2. `User.discord_notify_user_id` matches that account’s `uid`, and `discord_notify_verified_at` is set.

Linking or refreshing Discord login syncs these fields (see `users.signals`). `PATCH /api/auth/discord/notifications/` re-runs the same sync from the linked `SocialAccount`.

Other features (e.g. [mesh monitoring](../mesh-monitoring/README.md) offline alerts) should use the same rules before calling `send_dm`.

## Notification kinds

Every DM attempt (sent, skipped or failed) is recorded in `DiscordNotificationAudit` with a `feature` and a `kind` (`push_notifications.constants`).

| Feature | Kind | When |
|---------|------|------|
| `node_watch` | `node_offline`, `verification_started`, `node_battery_low` | [Mesh monitoring](../mesh-monitoring/README.md) watches |
| `dx_monitoring` | `dx_*` | DX monitoring (opt-in) |
| `feeder_identity` | `feeder_identity_changed` | A feeder's node number was re-pointed automatically. Sent to the feeder's owner: "Your feeder <name> changed node number: !old is now !new. It keeps its history and API key. Nothing to do." |
| `feeder_identity` | `feeder_identity_flagged` | A feeder reported a new node number that could not be applied automatically. Sent to the owner with the reason and "Open My Nodes to review it." |

See [Managed nodes](../node-lifecycle/managed-nodes.md#node-number-changes-28) for the feeder events. Manual re-points and `key_changed` events send no DM.

## Bot setup

1. Create a **Discord Application** (can be the same project as OAuth or a dedicated “Meshflow notifier” bot).
2. Create a **Bot** user and copy the **Bot Token** into `DISCORD_BOT_TOKEN`.
3. Invite the bot with a scope that allows it to DM users who share a server with the bot (typical `bot` scope). Users must share at least one guild with the bot for Discord to allow opening a DM channel, unless you use a different Discord product flow.

## HTTP API (prefs + test)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/auth/discord/notifications/` | `discord_linked`, `discord_notify_verified` |
| `PATCH` | `/api/auth/discord/notifications/` | Re-sync from linked Discord account |
| `POST` | `/api/auth/discord/notifications/test/` | Send a short test DM (requires verified + bot token) |

See `openapi.yaml` for responses and error codes.

## Environment

Documented in [`docs/ENV_VARS.md`](../../ENV_VARS.md): `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, and OAuth callback URLs.
