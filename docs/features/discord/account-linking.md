# Discord account linking (Meshflow)

This document describes how a Meshflow **user** is associated with a **Discord user** for **outbound direct messages** (bot token), and how that differs from using Discord **only** as a sign-in provider.

## Separate from “user auth,” but can use the same Discord account

- **Authentication** answers: *which Meshflow user is this session?* Providers include Google, GitHub, and Discord. See [`docs/AUTH.md`](../../AUTH.md) for the OAuth code flow, callbacks, and JWT exchange.
- **Account linking (this doc)** answers: *which Discord snowflake may receive DMs from Meshflow?* The API must not DM arbitrary IDs; linking + verification prove control of that Discord account.

You can:

- **Log in with Discord** — Meshflow creates or finds a user via `SocialAccount(provider=discord)`. Notify fields can be synced from that same account (see below).
- **Log in with Google (or another provider) and link Discord** — While holding a normal JWT, you complete a **connect** OAuth flow so `SocialAccount(provider=discord)` attaches to **your current** Meshflow user. That is the supported way to use Discord for DMs without using Discord as your primary login.

So: Discord **login** and Discord **linking** share OAuth machinery, but **enabling DMs** is a distinct concern (verified `discord_notify_*` fields + [Notifications](notifications.md)).

## Where it lives in code

| Concern | Django app / module |
|---------|---------------------|
| Discord **bot** REST (open DM channel, send message) | **`push_notifications`** — `push_notifications.discord` (`send_dm`, `DiscordSendError`, `DISCORD_BOT_TOKEN`) |
| OAuth “Login with Discord”, **connect** flow, `SocialAccount`, sync of `discord_notify_*` on **User** | **`users`** — `discord_sync`, signals, login/connect views |
| Notification **prefs** and **test** HTTP API (`/api/auth/discord/notifications/…`) | **`users`** — `views_discord` (calls `push_notifications.discord` to send) |

## Flows

### 1. Login with Discord

Uses the existing social pipeline: `/api/auth/social/discord/` → provider → callback → frontend exchanges code via `POST /api/auth/social/discord/token/` (see [`AUTH.md`](../../AUTH.md)). After login, signals / `DiscordLoginView` can sync `discord_notify_user_id` and verification from the linked `SocialAccount`.

### 2. Link Discord while signed in another way

For users who authenticated with Google, GitHub, password, etc.:

1. `GET /api/auth/social/discord/connect/` with **Bearer JWT** returns an `authorization_url` whose redirect is  
   `{CALLBACK_URL_BASE}/api/auth/social/discord/connect/callback/`.
2. After the user authorizes Discord, the backend attaches `SocialAccount(provider=discord)` to **that** Meshflow user (signed `state` + one-time nonce), runs the same notify-field sync as login, and redirects the browser to the SPA with `?token=` (fresh JWT).

If that Discord user id is already linked to a **different** Meshflow account, the callback redirects with `?error=discord_connect_account_in_use`.

### 3. Prefs and test DM

HTTP API and verification rules: [Notifications](notifications.md). Mesh monitoring and other features **consume** the same verified binding; they do not implement a second Discord OAuth stack.

## Data model (conceptual)

- **`SocialAccount`** (django-allauth) — `provider=discord`, `uid` = Discord user id string.
- **`User.discord_notify_user_id`**, **`User.discord_notify_verified_at`** — must match the linked account and be set before the API sends DMs (including the test endpoint). `PATCH /api/auth/discord/notifications/` re-syncs from `SocialAccount`.

## Security intent

- No DMs to a snowflake the user has not proven they control (OAuth link + matching uid + verified timestamp).
- Bot token stays server-side (`DISCORD_BOT_TOKEN`); not the same credential as OAuth client secret.
