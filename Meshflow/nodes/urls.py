from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import APIKeyViewSet

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'', NodeViewSet, basename='constellation')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
    path('<int:constellation_id>/api-keys/',
         APIKeyViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='constellation-api-keys'),
    path('<int:constellation_id>/api-keys/<uuid:pk>/',
         APIKeyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
         name='constellation-api-key-detail'),
    path('<int:constellation_id>/api-keys/<uuid:pk>/add-node/',
         APIKeyViewSet.as_view({'post': 'add_node'}),
         name='constellation-api-key-add-node'),
    path('<int:constellation_id>/api-keys/<uuid:pk>/remove-node/',
         APIKeyViewSet.as_view({'post': 'remove_node'}),
         name='constellation-api-key-remove-node'),
]
