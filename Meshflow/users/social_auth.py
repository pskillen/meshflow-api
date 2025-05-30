import uuid
from types import SimpleNamespace

from django.conf import settings
from django.shortcuts import redirect

import requests
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


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


class CompatibleOAuth2Client(OAuth2Client):
    """
    This class is required because dj-rest-auth calls OAuth2Client.__init__() with 9 arguments,
    but allauth.socialaccount.providers.oauth2.client.OAuth2Client.__init__() only accepts 8.
    """

    def __init__(
        self,
        request,
        consumer_key,
        consumer_secret,
        access_token_method,
        access_token_url,
        callback_url,
        scope,
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
