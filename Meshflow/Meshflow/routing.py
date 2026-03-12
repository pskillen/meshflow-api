from django.urls import path

from ws.consumers import NodeConsumer, TextMessageConsumer

websocket_urlpatterns = [
    path("ws/messages/", TextMessageConsumer.as_asgi()),
    path("ws/nodes/", NodeConsumer.as_asgi()),
]
