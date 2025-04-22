"""URL configuration for the packets app."""

from django.urls import path
from .views import PacketIngestView

urlpatterns = [
    path('ingest/', PacketIngestView.as_view(), name='packet-ingest'),
]
