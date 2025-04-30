from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Constellation, ConstellationUserMembership
from .serializers import ConstellationSerializer


class IsConstellationAdminOrEditor(permissions.BasePermission):
    """
    Permission to only allow admins or editors of a constellation to modify it.
    Anyone can create a new constellation.
    """

    def has_permission(self, request, view):
        # Allow GET requests for listing constellations
        if request.method in permissions.SAFE_METHODS:
            return True

        # Allow POST requests for creating new constellations
        if request.method == "POST" and view.action == "create":
            return True

        # For other methods, check if the user is an admin or editor of the constellation
        constellation_id = view.kwargs.get("pk")
        if not constellation_id:
            return False

        return ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation_id=constellation_id,
            role__in=["admin", "editor"],
        ).exists()

    def has_object_permission(self, request, view, obj):
        # Allow GET requests
        if request.method in permissions.SAFE_METHODS:
            # Check if user is a member of the constellation
            return ConstellationUserMembership.objects.filter(user=request.user, constellation=obj).exists()

        # For modifications, check if the user is an admin or editor
        return ConstellationUserMembership.objects.filter(
            user=request.user, constellation=obj, role__in=["admin", "editor"]
        ).exists()


class ConstellationViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows constellations to be viewed or edited.
    Users can only see constellations they are members of.
    """

    serializer_class = ConstellationSerializer
    permission_classes = [permissions.IsAuthenticated, IsConstellationAdminOrEditor]
    queryset = Constellation.objects.all().order_by("id")

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

    @action(detail=True, methods=["post"])
    def members(self, request, pk=None):
        """
        Manage constellation members.
        """
        constellation = self.get_object()

        # Only admins can manage members
        if not ConstellationUserMembership.objects.filter(
            user=request.user, constellation=constellation, role="admin"
        ).exists():
            return Response({"detail": "Only admins can manage members."}, status=status.HTTP_403_FORBIDDEN)

        members_data = request.data.get("members", [])

        # Clear existing memberships (except admin)
        ConstellationUserMembership.objects.filter(constellation=constellation).exclude(user=request.user).delete()

        # Create new memberships
        for member_data in members_data:
            user_id = member_data.get("user")
            role = member_data.get("role")

            if user_id and role:
                ConstellationUserMembership.objects.create(user_id=user_id, constellation=constellation, role=role)

        return Response(status=status.HTTP_200_OK)
