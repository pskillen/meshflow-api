import json
import logging

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)


class NodeConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for ManagedNode bots.

    Bots connect with NodeAPIKey via query param: ws/nodes/?api_key=<key>
    On connect, the bot joins group node_{node_id} and receives commands
    (e.g. traceroute) pushed via the channel layer.
    """

    async def connect(self):
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        query_params = dict(param.split("=", 1) for param in query_string.split("&") if "=" in param)
        api_key = query_params.get("api_key")

        if not api_key:
            logger.warning("NodeConsumer: missing api_key in query string")
            await self.close()
            return

        feeder_pubkey_prefix = query_params.get("feeder_pubkey_prefix")
        feeder_node_id_raw = query_params.get("feeder_node_id")
        feeder_node_id_str = query_params.get("feeder_node_id_str")
        feeder_node_id = None
        if feeder_node_id_raw is not None:
            try:
                feeder_node_id = int(feeder_node_id_raw)
            except ValueError:
                logger.warning(
                    "NodeConsumer: invalid feeder_node_id=%s",
                    feeder_node_id_raw,
                )
                await self.close()
                return

        managed_node = await self._validate_api_key(
            api_key,
            feeder_pubkey_prefix=feeder_pubkey_prefix,
            feeder_node_id=feeder_node_id,
            feeder_node_id_str=feeder_node_id_str,
        )
        if not managed_node:
            logger.warning(
                "NodeConsumer: invalid api_key feeder_pubkey_prefix=%s " "feeder_node_id=%s feeder_node_id_str=%s",
                feeder_pubkey_prefix,
                feeder_node_id,
                feeder_node_id_str,
            )
            await self.close()
            return

        from common.ws_groups import managed_node_ws_group

        self.managed_node = managed_node
        self.node_group = managed_node_ws_group(managed_node)

        await self.channel_layer.group_add(self.node_group, self.channel_name)
        await self.accept()
        logger.info(
            "NodeConsumer: bot connected for %s group=%s",
            managed_node.node_id_str,
            self.node_group,
        )

    async def disconnect(self, close_code):
        if hasattr(self, "node_group"):
            await self.channel_layer.group_discard(self.node_group, self.channel_name)
        managed_node = getattr(self, "managed_node", None)
        node_id = getattr(managed_node, "meshtastic_node_id", "unknown") if managed_node else "unknown"
        logger.info(f"NodeConsumer: bot disconnected for node {node_id}")

    async def receive(self, text_data):
        pass

    async def node_command(self, event):
        """Handle node_command messages from the channel layer."""
        command = event.get("command", {})
        logger.info(f"NodeConsumer: forwarding command to bot: {command}")
        await self.send(text_data=json.dumps(command))

    @database_sync_to_async
    def _validate_api_key(
        self,
        api_key,
        feeder_pubkey_prefix=None,
        feeder_node_id=None,
        feeder_node_id_str=None,
    ):
        """Validate NodeAPIKey and return the linked ManagedNode, or None."""
        from common.meshcore_feeder_auth import (
            MeshCoreFeederResolutionError,
            resolve_meshcore_feeder,
        )
        from common.meshtastic_feeder_auth import (
            MeshtasticFeederResolutionError,
            resolve_meshtastic_feeder,
        )
        from common.protocol import Protocol
        from nodes.models import NodeAPIKey, NodeAuth

        try:
            key_obj = NodeAPIKey.objects.get(key=api_key, is_active=True)
            key_obj.last_used = timezone.now()
            key_obj.save(update_fields=["last_used"])

            has_mc_disambiguator = bool(feeder_pubkey_prefix)
            has_mt_disambiguator = feeder_node_id is not None or bool(feeder_node_id_str)
            if has_mc_disambiguator and has_mt_disambiguator:
                logger.warning(
                    "NodeConsumer: pass feeder_pubkey_prefix or feeder_node_id, not both",
                )
                return None

            if feeder_pubkey_prefix:
                try:
                    return resolve_meshcore_feeder(
                        api_key=key_obj,
                        feeder_pubkey_prefix=feeder_pubkey_prefix,
                    )
                except MeshCoreFeederResolutionError:
                    return None

            if has_mt_disambiguator:
                try:
                    return resolve_meshtastic_feeder(
                        api_key=key_obj,
                        feeder_node_id=feeder_node_id,
                        feeder_node_id_str=feeder_node_id_str,
                    )
                except MeshtasticFeederResolutionError:
                    return None

            auths = list(
                NodeAuth.objects.filter(
                    api_key=key_obj,
                    node__deleted_at__isnull=True,
                ).select_related("node")
            )
            if not auths:
                return None

            mc_auths = [a for a in auths if a.node.protocol == Protocol.MESHCORE]
            mt_auths = [a for a in auths if a.node.protocol == Protocol.MESHTASTIC]

            if len(mc_auths) > 1:
                logger.warning(
                    "NodeConsumer: API key linked to %s MC feeders; " "pass feeder_pubkey_prefix on ws/nodes/",
                    len(mc_auths),
                )
                return None

            if len(mt_auths) > 1:
                logger.warning(
                    "NodeConsumer: API key linked to %s MT feeders; "
                    "pass feeder_node_id or feeder_node_id_str on ws/nodes/",
                    len(mt_auths),
                )
                return None

            if len(auths) > 1:
                logger.warning(
                    "NodeConsumer: API key linked to %s feeders; "
                    "pass feeder_pubkey_prefix (MC) or feeder_node_id (MT)",
                    len(auths),
                )
                return None

            return auths[0].node
        except NodeAPIKey.DoesNotExist:
            pass
        except Exception as e:
            logger.exception("NodeConsumer: error validating api_key: %s", e)
        return None


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


class TracerouteConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for traceroute status updates.

    Authenticated users connect with JWT via query param: ws/traceroutes/?token=<jwt>
    On connect, join group "traceroutes". Receive traceroute_update events when
    a traceroute is enqueued (pending) or its status changes (e.g. sent, completed, failed).
    """

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())

        query_string = self.scope.get("query_string", b"").decode("utf-8")
        query_params = dict(param.split("=", 1) for param in query_string.split("&") if "=" in param)
        token = query_params.get("token")

        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token.get("user_id")
                if user_id:
                    self.user = await self.get_user_from_id(user_id)
            except (TokenError, InvalidToken) as e:
                logger.warning("TracerouteConsumer: invalid token: %s", e)
                await self.close()
                return

        if self.user.is_anonymous:
            logger.warning("TracerouteConsumer: anonymous user tried to connect")
            await self.close()
            return

        await self.channel_layer.group_add("traceroutes", self.channel_name)
        await self.accept()
        logger.info("TracerouteConsumer: user %s connected", self.user.username)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("traceroutes", self.channel_name)
        logger.info("TracerouteConsumer: user %s disconnected", getattr(self.user, "username", "unknown"))

    async def receive(self, text_data):
        pass

    async def traceroute_update(self, event):
        """Handle traceroute_update from channel layer. Forward {id, status} to client."""
        await self.send(text_data=json.dumps({"id": event["id"], "status": event["status"]}))

    @database_sync_to_async
    def get_user_from_id(self, user_id):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return AnonymousUser()


class NodeClaimConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for node-claim acceptance (ownership proof).

    Authenticated users connect with JWT via query param: ws/claims/?token=<jwt>
    On connect, join group user_claims_{user_id}. Receive node_claim_update when
    a pending claim is accepted via mesh DM proof.
    """

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())

        query_string = self.scope.get("query_string", b"").decode("utf-8")
        query_params = dict(param.split("=", 1) for param in query_string.split("&") if "=" in param)
        token = query_params.get("token")

        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token.get("user_id")
                if user_id:
                    self.user = await self.get_user_from_id(user_id)
            except (TokenError, InvalidToken) as e:
                logger.warning("NodeClaimConsumer: invalid token: %s", e)
                await self.close()
                return

        if self.user.is_anonymous:
            logger.warning("NodeClaimConsumer: anonymous user tried to connect")
            await self.close()
            return

        from common.ws_groups import user_claims_ws_group

        self.claims_group = user_claims_ws_group(self.user.id)
        await self.channel_layer.group_add(self.claims_group, self.channel_name)
        await self.accept()
        logger.info("NodeClaimConsumer: user %s connected", self.user.username)

    async def disconnect(self, close_code):
        if hasattr(self, "claims_group"):
            await self.channel_layer.group_discard(self.claims_group, self.channel_name)
        logger.info(
            "NodeClaimConsumer: user %s disconnected",
            getattr(self.user, "username", "unknown"),
        )

    async def receive(self, text_data):
        pass

    async def node_claim_update(self, event):
        """Handle node_claim_update from channel layer."""
        await self.send(text_data=json.dumps(event["payload"]))

    @database_sync_to_async
    def get_user_from_id(self, user_id):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return AnonymousUser()
