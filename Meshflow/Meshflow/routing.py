from django.urls import path

from text_messages.consumers import TextMessageConsumer

websocket_urlpatterns = [
    path("ws/messages/", TextMessageConsumer.as_asgi()),
]
