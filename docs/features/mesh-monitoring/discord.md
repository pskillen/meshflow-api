# Discord notifications (Meshflow API)

See also: [Discord account linking](../discord-account-linking.md) (OAuth connect flow vs login).

User-facing Discord **direct messages** use a **bot token** (`DISCORD_BOT_TOKEN`), separate from **Discord OAuth** (`DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET`) used for “Login with Discord” and for **linking** Discord to an existing account (`/api/auth/social/discord/connect/`).

## Verify ownership (anti-spam)

The API only sends DMs (including the **test** endpoint) when:

1. The user has linked Discord via OAuth (django-allauth `SocialAccount` with `provider=discord`).
2. `User.discord_notify_user_id` matches that account’s `uid`, and `discord_notify_verified_at` is set.

Linking or refreshing Discord login syncs these fields (see `users.signals`). `PATCH /api/auth/discord/notifications/` re-runs the same sync from the linked `SocialAccount`.

## Bot setup

1. Create a **Discord Application** (can be the same project as OAuth or a dedicated “Meshflow notifier” bot).
2. Create a **Bot** user and copy the **Bot Token** into `DISCORD_BOT_TOKEN`.
3. Invite the bot with a scope that allows it to DM users who share a server with the bot (typical `bot` scope + **applications.commands** if you add slash commands later). Users must share at least one guild with the bot for Discord to allow opening a DM channel, unless you use a different Discord product flow.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/auth/discord/notifications/` | `discord_linked`, `discord_notify_verified` |
| `PATCH` | `/api/auth/discord/notifications/` | Re-sync from linked Discord account |
| `POST` | `/api/auth/discord/notifications/test/` | Send a short test DM (requires verified + bot token) |

See `openapi.yaml` for responses and error codes.
