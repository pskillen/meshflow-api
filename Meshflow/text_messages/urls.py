from django.urls import path

from rest_framework.routers import DefaultRouter

from .unread import ChannelMarkReadView, UnreadCountsView
from .views import TextMessageViewSet

router = DefaultRouter()
router.register(r"text", TextMessageViewSet, basename="textmessage")

urlpatterns = [
    path("unread-counts/", UnreadCountsView.as_view(), name="message-unread-counts"),
    path("channels/<int:channel_id>/mark-read/", ChannelMarkReadView.as_view(), name="message-channel-mark-read"),
] + router.urls
