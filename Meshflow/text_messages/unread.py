"""Server-side unread state: per-user channel read cursors and unread counts."""

import uuid
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework.response import Response
from rest_framework.views import APIView

from common.drf_permissions import IsAuthenticatedUser
from common.protocol import Protocol
from constellations.models import MessageChannel

from .models import MessageChannelReadState, TextMessage
from .views import CHANNEL_MESSAGE_Q

UNREAD_CAP_PER_CHANNEL = 99
UNREAD_WINDOW = timedelta(days=7)

PROTOCOL_KEYS = {Protocol.MESHTASTIC: "meshtastic", Protocol.MESHCORE: "meshcore"}


def visible_channels():
    """Channels a user may see. The messages list endpoint applies no per-user scoping, so all channels."""
    return MessageChannel.objects.all()


class UnreadCountsView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        user = request.user
        now = timezone.now()
        channels = list(visible_channels().values_list("id", "protocol"))
        existing = set(MessageChannelReadState.objects.filter(user=user).values_list("channel_id", flat=True))
        missing = [cid for cid, _protocol in channels if cid not in existing]
        if missing:
            # First sight of a channel: start the cursor at now so nobody begins with a backlog.
            MessageChannelReadState.objects.bulk_create(
                [MessageChannelReadState(user=user, channel_id=cid, last_read_at=now) for cid in missing],
                ignore_conflicts=True,
            )

        rows = (
            TextMessage.objects.filter(
                CHANNEL_MESSAGE_Q,
                Q(sent_at__gt=now - UNREAD_WINDOW) & Q(sent_at__gt=F("channel__read_states__last_read_at")),
                channel__read_states__user=user,
            )
            .values("channel_id")
            .annotate(n=Count("id"))
        )
        counts = {r["channel_id"]: min(r["n"], UNREAD_CAP_PER_CHANNEL) for r in rows}

        result = {key: {"total": 0, "channels": {}} for key in PROTOCOL_KEYS.values()}
        for cid, protocol in channels:
            n = counts.get(cid, 0)
            key = PROTOCOL_KEYS.get(protocol)
            if n and key:
                result[key]["channels"][str(cid)] = n
                result[key]["total"] += n
        return Response(result)


class ChannelMarkReadView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request, channel_id):
        channel = get_object_or_404(visible_channels(), pk=channel_id)
        now = timezone.now()
        up_to = request.data.get("up_to")
        target = now
        if up_to not in (None, ""):
            target = self._resolve_up_to(channel, str(up_to))
            if target is None:
                return Response(
                    {"detail": "up_to must be an ISO timestamp or a message id in this channel."}, status=400
                )
            target = min(target, now)

        state, created = MessageChannelReadState.objects.get_or_create(
            user=request.user, channel=channel, defaults={"last_read_at": target}
        )
        if not created:
            # Conditional update: the cursor only ever moves forward, even under concurrent requests.
            MessageChannelReadState.objects.filter(pk=state.pk, last_read_at__lt=target).update(last_read_at=target)
            state.refresh_from_db()
        return Response({"channel_id": channel.pk, "last_read_at": state.last_read_at})

    @staticmethod
    def _resolve_up_to(channel, value):
        try:
            msg_id = uuid.UUID(value)
        except ValueError:
            msg_id = None
        if msg_id is not None:
            return TextMessage.objects.filter(pk=msg_id, channel=channel).values_list("sent_at", flat=True).first()
        try:
            parsed = parse_datetime(value)
        except ValueError:
            return None
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
