from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ObservedNodeViewSet, ManagedNodeViewSet, APIKeyViewSet

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'nodes', ObservedNodeViewSet, basename='nodes')
router.register(r'managed-nodes', ManagedNodeViewSet, basename='managed-nodes')
router.register(r'api-keys', APIKeyViewSet, basename='api-keys')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
]
