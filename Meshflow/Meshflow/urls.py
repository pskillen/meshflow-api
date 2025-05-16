"""
URL configuration for Meshflow project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from users.serializers import CustomTokenObtainPairView

from .views import StatusView

# API Documentation
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Meshflow API",
        default_version='v1',
        description="Meshflow is a distributed telemetry collection system for Meshtastic radio networks",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url='/docs/', permanent=False), name='index'),
    path(
        "api/",
        include(
            [
                path("status/", StatusView.as_view(), name="status"),
                path("packets/", include("packets.urls")),
                path("constellations/", include("constellations.urls")),
                path("nodes/", include("nodes.urls")),
                path("stats/", include("stats.urls")),
                path("messages/", include("text_messages.urls")),
                # JWT Token endpoints
                path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
                path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
                path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
                # Social auth endpoints
                path("auth/", include("users.urls")),
            ]
        ),
    ),
    # API Documentation
    path('docs/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('openapi.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]

if settings.PROMETHEUS_PASSWORD:
    urlpatterns += [
        path("", include("django_prometheus.urls")),
    ]
