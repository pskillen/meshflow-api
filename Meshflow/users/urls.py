from django.urls import include, path

from users import views_discord
from users.social_auth import (
    DiscordCallbackRedirectView,
    DiscordConnectAuthView,
    DiscordConnectCallbackView,
    DiscordLoginRedirectView,
    DiscordLoginView,
    GithubCallbackRedirectView,
    GithubLoginRedirectView,
    GithubLoginView,
    GoogleCallbackRedirectView,
    GoogleLoginRedirectView,
    GoogleLoginView,
)

urlpatterns = [
    path(
        "discord/notifications/",
        views_discord.DiscordNotificationPrefsView.as_view(),
        name="discord-notification-prefs",
    ),
    path(
        "discord/notifications/test/",
        views_discord.DiscordTestNotificationView.as_view(),
        name="discord-notification-test",
    ),
    # dj-rest-auth endpoints
    path("", include("dj_rest_auth.urls")),
    # path("registration/", include("dj_rest_auth.registration.urls")),
    # Social auth endpoints
    # path("accounts/", include("allauth.urls")),
    path("social/google/", GoogleLoginRedirectView.as_view(), name="google_login"),
    path("social/google/callback/", GoogleCallbackRedirectView.as_view(), name="google_login_callback"),
    path("social/google/token/", GoogleLoginView.as_view(), name="google_token"),
    path("social/github/", GithubLoginRedirectView.as_view(), name="github_login"),
    path("social/github/callback/", GithubCallbackRedirectView.as_view(), name="github_login_callback"),
    path("social/github/token/", GithubLoginView.as_view(), name="github_token"),
    path("social/discord/connect/", DiscordConnectAuthView.as_view(), name="discord_connect_auth"),
    path(
        "social/discord/connect/callback/",
        DiscordConnectCallbackView.as_view(),
        name="discord_connect_callback",
    ),
    path("social/discord/", DiscordLoginRedirectView.as_view(), name="discord_login"),
    path("social/discord/callback/", DiscordCallbackRedirectView.as_view(), name="discord_login_callback"),
    path("social/discord/token/", DiscordLoginView.as_view(), name="discord_token"),
]
