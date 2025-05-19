import json
import logging

from django.contrib.auth.models import AnonymousUser

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)


class TextMessageConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for text messages.

    This consumer handles WebSocket connections for text messages.
    It authenticates users using JWT tokens and sends messages to connected clients.
    """

    async def connect(self):
        """
        Called when the WebSocket is handshaking as part of the connection process.
        """
        self.user = self.scope.get("user", AnonymousUser())

        # Get token from query string
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        query_params = dict(param.split("=") for param in query_string.split("&") if "=" in param)
        token = query_params.get("token", None)

        # Authenticate with token if provided
        if token:
            try:
                # Validate the token
                access_token = AccessToken(token)
                user_id = access_token.get("user_id")

                # Get the user from the database
                if user_id:
                    self.user = await self.get_user_from_id(user_id)
            except (TokenError, InvalidToken) as e:
                logger.warning(f"Invalid token: {e}")
                await self.close()
                return

        # Reject the connection if the user is not authenticated
        if self.user.is_anonymous:
            logger.warning("Anonymous user tried to connect to WebSocket")
            await self.close()
            return

        # Add the user to the messages group
        await self.channel_layer.group_add("text_messages", self.channel_name)

        # Accept the connection
        await self.accept()
        logger.info(f"WebSocket connection established for user {self.user.username}")

    async def disconnect(self, close_code):
        """
        Called when the WebSocket closes for any reason.
        """
        # Remove the user from the messages group
        await self.channel_layer.group_discard("text_messages", self.channel_name)
        logger.info(f"WebSocket connection closed for user {getattr(self.user, 'username', 'unknown')}")

    async def receive(self, text_data):
        """
        Called when we get a text frame from the client.
        """
        # We don't expect to receive any messages from the client
        pass

    async def text_message(self, event):
        """
        Called when a message is received from the channel layer.
        """
        # Send the message to the WebSocket
        print(f"Forwarding to WS message: {event['message']}")
        await self.send(text_data=json.dumps(event["message"]))

    @database_sync_to_async
    def get_user_from_id(self, user_id):
        """
        Get a user from the database by ID.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return AnonymousUser()
