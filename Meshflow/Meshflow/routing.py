from django.urls import path

from ws.consumers import TextMessageConsumer

websocket_urlpatterns = [
    path("ws/messages/", TextMessageConsumer.as_asgi()),
]
