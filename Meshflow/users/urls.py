from django.urls import include, path

from users.social_auth import (
    GoogleLoginRedirectView,
    GoogleCallbackRedirectView,
    GithubLoginRedirectView,
    GithubCallbackRedirectView,
    GoogleLoginView,
    GithubLoginView,
)

urlpatterns = [
    # dj-rest-auth endpoints
    path("", include("dj_rest_auth.urls")),
    path("registration/", include("dj_rest_auth.registration.urls")),
    # Social auth endpoints
    path("accounts/", include("allauth.urls")),
    path("social/google/", GoogleLoginRedirectView.as_view(), name="google_login"),
    path("social/google/callback/", GoogleCallbackRedirectView.as_view(), name="google_login_callback"),
    path("social/google/token/", GoogleLoginView.as_view(), name="google_token"),
    path("social/github/", GithubLoginRedirectView.as_view(), name="github_login"),
    path("social/github/callback/", GithubCallbackRedirectView.as_view(), name="github_login_callback"),
    path("social/github/token/", GithubLoginView.as_view(), name="github_token"),
]
