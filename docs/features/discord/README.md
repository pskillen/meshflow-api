# Discord (Meshflow)

Meshflow uses Discord in **two independent ways**:

1. **Social login** — “Sign in with Discord” is one of several OAuth providers. That flow is documented in [`docs/AUTH.md`](../../AUTH.md). It establishes **who you are** in Meshflow (session/JWT).
2. **Account linking + notifications** — You can **link** a Discord account to your Meshflow user so the API can send you **direct messages** via a **bot token** (prefs, test DM, and future alerts such as mesh-monitoring offline notices). That is documented in this folder.

Linking and notification prefs are **not** required to use Discord as a login provider, and logging in with Discord does not by itself enable DMs until the notify fields are verified (see [Notifications](notifications.md)).

## Docs in this folder

| Document | What it covers |
|----------|----------------|
| [Account linking](account-linking.md) | Connect vs login, `SocialAccount`, sync of `discord_notify_*`, eligibility for DMs |
| [Notifications](notifications.md) | Bot transport (`push_notifications`), verified-only DMs, prefs + test HTTP API, bot setup |

## Related feature docs

- [Mesh monitoring](../mesh-monitoring/README.md) — uses verified Discord DMs to alert users when a **watched** node is considered offline (runtime in development; see that doc for status).

## Code map (summary)

| Layer | Location |
|-------|----------|
| Bot DM HTTP (`DISCORD_BOT_TOKEN`) | `push_notifications.discord` |
| OAuth login/callback, connect-while-signed-in | `users` (allauth, `social_auth`, connect views) |
| Sync `discord_notify_*` from linked Discord | `users.discord_sync`, signals |
| Prefs + test routes | `users.views_discord` |

Environment variables: [`docs/ENV_VARS.md`](../../ENV_VARS.md) (`DISCORD_CLIENT_*`, `DISCORD_BOT_TOKEN`).
