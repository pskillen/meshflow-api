from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.socialaccount.models import SocialApp


class GoogleLoginView(SocialLoginView):

    permission_classes = []
    authentication_classes = []

    """
    View for Google OAuth2 authentication.
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = settings.CALLBACK_URL if hasattr(settings, 'CALLBACK_URL') else None
    client_class = OAuth2Client

    def get(self, request, *args, **kwargs):
        """
        Handle GET request by redirecting to Google OAuth authorization URL.
        """
        # Get the app credentials
        try:
            app = SocialApp.objects.get(provider='google', sites=settings.SITE_ID)
        except SocialApp.DoesNotExist:
            google_settings = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']
            from types import SimpleNamespace
            app = SimpleNamespace(
                client_id=google_settings['client_id'],
                secret=google_settings['secret']
            )

        adapter = self.adapter_class(request)
        provider = adapter.get_provider()
        client = self.client_class(
            request=request,
            consumer_key=app.client_id,
            consumer_secret=app.secret,
            access_token_url=adapter.access_token_url,
            access_token_method=adapter.access_token_method,
            callback_url=self.callback_url,
        )

        # Get the authorization URL
        auth_url = client.get_redirect_url(
            adapter.authorize_url,
            provider.get_scope(),
            provider.get_auth_params(),
        )

        # Redirect to the authorization URL
        return Response({'authorization_url': auth_url}, status=status.HTTP_200_OK)


class GoogleAuthToken(APIView):
    """
    Exchange Google access token for JWT tokens.
    """
    permission_classes = []

    def post(self, request, *args, **kwargs):
        """
        Exchange Google access token for JWT tokens.
        """
        access_token = request.data.get('access_token')
        if not access_token:
            return Response(
                {'error': 'Access token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the adapter to validate the token and get the user
        adapter = GoogleOAuth2Adapter()
        try:
            try:
                app = SocialApp.objects.get(provider='google', sites=settings.SITE_ID)
            except SocialApp.DoesNotExist:
                google_settings = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']
                from types import SimpleNamespace
                app = SimpleNamespace(
                    client_id=google_settings['client_id'],
                    secret=google_settings['secret']
                )
            token = adapter.parse_token({'access_token': access_token})
            token_user = adapter.get_provider().sociallogin_from_response(
                request, {'access_token': access_token}
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create the user
        user = token_user.user
        if not user.is_active:
            return Response(
                {'error': 'User account is disabled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'display_name': user.display_name,
            }
        })
