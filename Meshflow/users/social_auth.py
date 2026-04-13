import logging
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.shortcuts import redirect

import requests
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.discord.views import DiscordOAuth2Adapter
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


class BaseLoginRedirectView(APIView):
    permission_classes = []
    authentication_classes = []

    callback_url_base = settings.CALLBACK_URL_BASE if hasattr(settings, "CALLBACK_URL_BASE") else None
    client_class = OAuth2Client

    provider_name: str = None
    adapter_class = None

    def get(self, request, *args, **kwargs):
        """
        Handle GET request by redirecting to Google OAuth authorization URL.
        """
        # Get the app credentials
        try:
            app = SocialApp.objects.get(provider=self.provider_name, sites=settings.SITE_ID)
        except SocialApp.DoesNotExist:
            provider_settings = settings.SOCIALACCOUNT_PROVIDERS[self.provider_name]["APP"]
            app = SimpleNamespace(
                client_id=provider_settings["client_id"],
                secret=provider_settings["secret"],
            )

        adapter = self.adapter_class(request)
        provider = adapter.get_provider()
        client = self.client_class(
            request=request,
            consumer_key=app.client_id,
            consumer_secret=app.secret,
            access_token_url=adapter.access_token_url,
            access_token_method=adapter.access_token_method,
            callback_url=f"{self.callback_url_base}/api/auth/social/{self.provider_name}/callback/",
        )

        # Generate state and store in session
        state = f"{self.provider_name}:{uuid.uuid4().hex}"
        request.session["oauth2_state"] = state
        request.session.modified = True

        auth_params = provider.get_auth_params()
        auth_params["state"] = state

        # Get the authorization URL
        auth_url = client.get_redirect_url(
            adapter.authorize_url,
            provider.get_scope(),
            auth_params,
        )

        # Redirect to the authorization URL
        return Response({"authorization_url": auth_url}, status=status.HTTP_200_OK)


class GoogleLoginRedirectView(BaseLoginRedirectView):
    """
    View for Google OAuth2 authentication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "google"
        self.adapter_class = GoogleOAuth2Adapter


class GithubLoginRedirectView(BaseLoginRedirectView):
    """
    View for Github OAuth2 authentication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "github"
        self.adapter_class = GitHubOAuth2Adapter


class DiscordLoginRedirectView(BaseLoginRedirectView):
    """
    View for Discord OAuth2 authentication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "discord"
        self.adapter_class = DiscordOAuth2Adapter


class CompatibleOAuth2Client(OAuth2Client):
    """
    Compatibility shim for dj-rest-auth and django-allauth OAuth2Client.
    Accepts both legacy (9-arg, with scope) and current (8-arg, no scope) call signatures.
    Scope is not used in __init__ (parent receives it in get_redirect_url).
    """

    def __init__(
        self,
        request,
        consumer_key,
        consumer_secret,
        access_token_method,
        access_token_url,
        callback_url,
        scope=None,  # Optional: dj-rest-auth 7.0.2+ no longer passes scope
        scope_delimiter=" ",
        headers=None,
        basic_auth=False,
    ):
        super().__init__(
            request,
            consumer_key,
            consumer_secret,
            access_token_method,
            access_token_url,
            callback_url,
            scope_delimiter,
            headers,
            basic_auth,
        )


class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = CompatibleOAuth2Client
    callback_url = settings.CALLBACK_URL_BASE + "/api/auth/social/google/callback/"


class GithubLoginView(SocialLoginView):
    adapter_class = GitHubOAuth2Adapter
    client_class = CompatibleOAuth2Client
    callback_url = settings.CALLBACK_URL_BASE + "/api/auth/social/github/callback/"


class DiscordLoginView(SocialLoginView):
    adapter_class = DiscordOAuth2Adapter
    client_class = CompatibleOAuth2Client
    callback_url = settings.CALLBACK_URL_BASE + "/api/auth/social/discord/callback/"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and getattr(self, "user", None):
            from users.discord_sync import sync_discord_notify_from_social_accounts

            sync_discord_notify_from_social_accounts(self.user)
        return response


class BaseCallbackView(APIView):
    """
    Handles OAuth2 callback: exchanges code for access token, logs in user, issues JWT, redirects to frontend.
    """

    permission_classes = []

    callback_url_base = settings.CALLBACK_URL_BASE if hasattr(settings, "CALLBACK_URL_BASE") else None
    provider_name: str = None
    adapter_class = None

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code")
        state = request.GET.get("state")
        if not code:
            return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

        # session_state = request.session.get("oauth2_state")
        if not state:  # or state != session_state:
            return Response({"error": "Invalid state"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Exchange code for access token
        token_url, client_id, client_secret, redirect_uri = self.get_provider_config(request)
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Accept": "application/json"}
        token_resp = requests.post(token_url, data=data, headers=headers)
        if not token_resp.ok:
            return Response({"error": "Failed to get access token", "details": token_resp.text}, status=400)
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return Response({"error": "No access token in response"}, status=400)

        # 2. Use the access token to complete login
        adapter = self.adapter_class(request)
        try:
            token = adapter.parse_token({"access_token": access_token})
            token_user = adapter.complete_login(
                request=request, app=adapter.get_provider(), token=token, response=token_resp.json()
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user = token_user.user
        if not user.is_active:
            return Response({"error": "User account is disabled"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        jwt_token = str(refresh.access_token)

        # 4. Redirect to frontend with token
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
        return redirect(f"{frontend_url}{settings.FRONTEND_OAUTH_CALLBACK_PATH}?token={jwt_token}")

    def get_provider_config(self, request):
        adapter = self.adapter_class(request)
        access_token_url = adapter.access_token_url
        callback_url = f"{self.callback_url_base}/api/auth/social/{self.provider_name}/callback/"

        try:
            app = SocialApp.objects.get(provider=self.provider_name, sites=settings.SITE_ID)
        except SocialApp.DoesNotExist:
            provider_settings = settings.SOCIALACCOUNT_PROVIDERS[self.provider_name]["APP"]
            app = SimpleNamespace(
                client_id=provider_settings["client_id"],
                secret=provider_settings["secret"],
            )

        return (
            access_token_url,
            app.client_id,
            app.secret,
            callback_url,
        )


class BaseCallbackRedirectView(APIView):
    """
    Handles OAuth2 callback: verified state and forwards code to frontend.
    """

    permission_classes = []

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code")
        state = request.GET.get("state")
        if not code:
            return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

        # session_state = request.session.get("oauth2_state")
        # if not state or state != session_state:
        #     return Response({"error": "Invalid state"}, status=status.HTTP_400_BAD_REQUEST)

        return redirect(f"{settings.FRONTEND_URL}{settings.FRONTEND_OAUTH_CALLBACK_PATH}?code={code}&state={state}")


class GoogleCallbackRedirectView(BaseCallbackRedirectView):
    """
    Handles Google OAuth2 callback: verified state and forwards code to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "google"
        self.adapter_class = GoogleOAuth2Adapter


class GithubCallbackRedirectView(BaseCallbackRedirectView):
    """
    Handles Github OAuth2 callback: verified state and forwards code to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "github"
        self.adapter_class = GitHubOAuth2Adapter


class DiscordCallbackRedirectView(BaseCallbackRedirectView):
    """
    Handles Discord OAuth2 callback: verified state and forwards code to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "discord"
        self.adapter_class = DiscordOAuth2Adapter


class GoogleCallbackView(BaseCallbackView):
    """
    Handles Google OAuth2 callback: exchanges code for access token, logs in user, issues JWT, redirects to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "google"
        self.adapter_class = GoogleOAuth2Adapter


class GithubCallbackView(BaseCallbackView):
    """
    Handles Github OAuth2 callback: exchanges code for access token, logs in user, issues JWT, redirects to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "github"
        self.adapter_class = GitHubOAuth2Adapter


class DiscordCallbackView(BaseCallbackView):
    """
    Handles Discord OAuth2 callback: exchanges code for access token, logs in user, issues JWT, redirects to frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_name = "discord"
        self.adapter_class = DiscordOAuth2Adapter


class DiscordConnectAuthView(APIView):
    """
    Authenticated: return Discord OAuth authorization URL to link Discord to the current Meshflow user.
    Uses a dedicated callback URL and signed state (see users.discord_connect_oauth).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from users.discord_connect_oauth import create_discord_connect_state

        try:
            app = SocialApp.objects.get(provider="discord", sites=settings.SITE_ID)
        except SocialApp.DoesNotExist:
            provider_settings = settings.SOCIALACCOUNT_PROVIDERS["discord"]["APP"]
            app = SimpleNamespace(
                client_id=provider_settings["client_id"],
                secret=provider_settings["secret"],
            )

        state = create_discord_connect_state(request.user.pk)
        callback_url = f"{settings.CALLBACK_URL_BASE.rstrip('/')}/api/auth/social/discord/connect/callback/"

        adapter = DiscordOAuth2Adapter(request)
        provider = adapter.get_provider()
        client = CompatibleOAuth2Client(
            request=request,
            consumer_key=app.client_id,
            consumer_secret=app.secret,
            access_token_url=adapter.access_token_url,
            access_token_method=adapter.access_token_method,
            callback_url=callback_url,
        )
        auth_params = provider.get_auth_params()
        auth_params["state"] = state

        auth_url = client.get_redirect_url(
            adapter.authorize_url,
            provider.get_scope(),
            auth_params,
        )
        return Response({"authorization_url": auth_url}, status=status.HTTP_200_OK)


class DiscordConnectCallbackView(APIView):
    """
    OAuth callback for Discord connect flow: attach Discord SocialAccount to signed user, issue JWT, redirect to SPA.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        from django.contrib.auth import get_user_model

        from users.discord_connect_oauth import (
            DiscordAccountAlreadyLinkedError,
            attach_discord_to_user,
            consume_discord_connect_state,
            fetch_discord_me,
        )
        from users.discord_sync import sync_discord_notify_from_social_accounts

        code = request.GET.get("code")
        state = request.GET.get("state")
        frontend = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
        callback_path = settings.FRONTEND_OAUTH_CALLBACK_PATH

        def fail_redirect(reason: str):
            return redirect(f"{frontend}{callback_path}?error=discord_connect_{reason}")

        if not code or not state:
            return fail_redirect("missing_params")

        try:
            user_id = consume_discord_connect_state(state)
        except ValueError:
            logger.info("Discord connect: invalid or replayed state")
            return fail_redirect("invalid_state")

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return fail_redirect("user_missing")

        if not user.is_active:
            return fail_redirect("disabled")

        token_url, client_id, client_secret, redirect_uri = _discord_connect_token_params(request)
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        token_resp = requests.post(token_url, data=data, headers={"Accept": "application/json"})
        if not token_resp.ok:
            logger.warning("Discord connect token exchange failed: %s", token_resp.text)
            return fail_redirect("token_exchange")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            return fail_redirect("no_access_token")

        try:
            discord_user = fetch_discord_me(access_token)
        except requests.RequestException as e:
            logger.warning("Discord connect @me failed: %s", e)
            return fail_redirect("discord_profile")

        try:
            attach_discord_to_user(user, discord_user)
        except DiscordAccountAlreadyLinkedError:
            return fail_redirect("account_in_use")

        sync_discord_notify_from_social_accounts(user)

        refresh = RefreshToken.for_user(user)
        jwt_token = str(refresh.access_token)
        return redirect(f"{frontend}{callback_path}?token={jwt_token}")


def _discord_connect_token_params(request):
    """Token endpoint URL, client credentials, and redirect_uri for connect callback (must match authorize step)."""
    adapter = DiscordOAuth2Adapter(request)
    access_token_url = adapter.access_token_url
    redirect_uri = f"{settings.CALLBACK_URL_BASE.rstrip('/')}/api/auth/social/discord/connect/callback/"

    try:
        app = SocialApp.objects.get(provider="discord", sites=settings.SITE_ID)
    except SocialApp.DoesNotExist:
        provider_settings = settings.SOCIALACCOUNT_PROVIDERS["discord"]["APP"]
        app = SimpleNamespace(
            client_id=provider_settings["client_id"],
            secret=provider_settings["secret"],
        )

    return access_token_url, app.client_id, app.secret, redirect_uri
