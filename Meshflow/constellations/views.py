from django.shortcuts import get_object_or_404

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from Meshflow.permissions import NoPermission

from .models import Constellation, ConstellationUserMembership, MessageChannel
from .permissions import IsConstellationAdmin, IsConstellationEditorOrAdmin, IsConstellationMember
from .serializers import ConstellationMemberSerializer, ConstellationSerializer, MessageChannelSerializer


class ConstellationViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows constellations to be viewed or edited.
    Users can only see constellations they are members of.

    Permissions:
    - GET /constellations/ - returns a list of any constellation for which the user is a member (regardless of role)
    - POST /constellations/ - only Django admins
    - GET /constellations/<id> - if member (any role)
    - PUT /constellations/<id>/ - if ConstellationMembership.role is admin
    - DELETE /constellations/<id>/ - Django admins
    """

    serializer_class = ConstellationSerializer
    queryset = Constellation.objects.all().order_by("id")

    def get_permissions(self):
        admin_permission = permissions.IsAdminUser()
        if self.action == "create":
            return [admin_permission]
        elif self.action == "list":
            return [permissions.AllowAny()]
        elif self.action == "retrieve":
            return [permissions.OR(admin_permission, IsConstellationMember())]
        elif self.action in ["update", "partial_update"]:
            return [permissions.OR(admin_permission, IsConstellationAdmin())]
        elif self.action == "destroy":
            return [admin_permission]
        else:
            return [NoPermission()]

    def get_queryset(self):
        """
        Return constellations that the user is a member of.
        """
        if self.action == "retrieve":
            # For single object retrieval, return all constellations to let permission classes handle access
            return Constellation.objects.all().order_by("id")

        # For list view, only return constellations the user is a member of
        return (
            Constellation.objects.filter(constellationusermembership__user=self.request.user).distinct().order_by("id")
        )

    def perform_create(self, serializer):
        """
        Create a new constellation and assign the creating user as an admin.
        """
        constellation = serializer.save()
        # Create membership for the creating user as admin
        ConstellationUserMembership.objects.create(user=self.request.user, constellation=constellation, role="admin")


class ConstellationMembersViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for managing constellation members.
    list: GET /constellations/<id>/members/ (if member)
    create: POST /constellations/<id>/members/ (if admin or editor)
    update: PUT /constellations/<id>/members/<user_id>/ (if admin or editor)
    destroy: DELETE /constellations/<id>/members/<user_id>/ (if admin or editor)
    """

    serializer_class = ConstellationMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        constellation_id = self.kwargs.get("constellation_id")
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        return ConstellationUserMembership.objects.filter(constellation=constellation).order_by("id")

    def get_permissions(self):
        admin_permission = permissions.IsAdminUser()
        if self.action == "list":
            return [permissions.OR(admin_permission, IsConstellationMember())]
        else:
            return [permissions.OR(admin_permission, IsConstellationEditorOrAdmin())]

    def create(self, request, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        members_data = request.data.get("members", [])
        for member_data in members_data:
            user_id = member_data.get("user")
            role = member_data.get("role")
            if user_id and role:
                ConstellationUserMembership.objects.update_or_create(
                    user_id=user_id, constellation=constellation, defaults={"role": role}
                )
        return Response(status=status.HTTP_200_OK)

    def update(self, request, pk=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        user_id = pk
        role = request.data.get("role")
        if not role:
            return Response({"detail": "Role is required."}, status=status.HTTP_400_BAD_REQUEST)
        membership, created = ConstellationUserMembership.objects.update_or_create(
            user_id=user_id, constellation=constellation, defaults={"role": role}
        )
        return Response(ConstellationMemberSerializer(membership).data)

    def destroy(self, request, user_id=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        if not user_id:
            return Response({"detail": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        if (
            str(user_id) == str(request.user.id)
            and ConstellationUserMembership.objects.filter(
                user=request.user, constellation=constellation, role="admin"
            ).exists()
        ):
            return Response({"detail": "Cannot remove yourself as an admin."}, status=status.HTTP_400_BAD_REQUEST)
        membership = ConstellationUserMembership.objects.filter(user_id=user_id, constellation=constellation)
        if membership.exists():
            membership.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"detail": "Membership not found."}, status=status.HTTP_404_NOT_FOUND)


class ConstellationMessageChannelsViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for managing message channels in a constellation.
    list: GET /constellations/<id>/channels/ (if member)
    create: POST /constellations/<id>/channels/ (if admin)
    update: PUT /constellations/<id>/channels/<pk>/ (if admin)
    destroy: DELETE /constellations/<id>/channels/<pk>/ (if admin)
    """

    serializer_class = MessageChannelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        constellation_id = self.kwargs.get("constellation_id")
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        return MessageChannel.objects.filter(constellation=constellation).order_by("id")

    def get_permissions(self):
        admin_permission = permissions.IsAdminUser()
        if self.action == "list":
            return [permissions.OR(admin_permission, IsConstellationMember())]
        else:
            return [permissions.OR(admin_permission, IsConstellationAdmin())]

    def create(self, request, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        data = request.data.copy()
        data["constellation"] = constellation.id
        serializer = MessageChannelSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, channel_id=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        try:
            channel = MessageChannel.objects.get(id=channel_id, constellation=constellation)
        except MessageChannel.DoesNotExist:
            return Response({"detail": "Channel not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        data["constellation"] = constellation.id
        serializer = MessageChannelSerializer(channel, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, channel_id=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        try:
            channel = MessageChannel.objects.get(id=channel_id, constellation=constellation)
        except MessageChannel.DoesNotExist:
            return Response({"detail": "Channel not found."}, status=status.HTTP_404_NOT_FOUND)
        channel.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
