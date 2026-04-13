# Discord account linking (Meshflow)

Atomic feature: associate a Meshflow user with a Discord user so the API can send **direct messages** via a bot token (`DISCORD_BOT_TOKEN`), independent of other product features.

## Flows

1. **Login with Discord** — existing `/api/auth/social/discord/` + callback + `POST .../token/`; creates session/JWT as today. `discord_notify_*` sync via signals / `DiscordLoginView`.
2. **Link Discord while signed in another way** — `GET /api/auth/social/discord/connect/` with **Bearer JWT** returns `authorization_url` using redirect  
   `{CALLBACK_URL_BASE}/api/auth/social/discord/connect/callback/`.  
   After authorization, the API attaches `SocialAccount(provider=discord)` to **that** user (signed OAuth `state` + one-time nonce), syncs notify fields, and redirects to the SPA with `?token=` (fresh JWT).

If the Discord user id is already linked to a **different** Meshflow account, the callback redirects with `?error=discord_connect_account_in_use`.

## Prefs + test DM

See [mesh-monitoring/discord.md](./mesh-monitoring/discord.md) for `GET/PATCH /api/auth/discord/notifications/` and `POST .../test/` (same HTTP contract; mesh-monitoring is one consumer of verified DMs).
