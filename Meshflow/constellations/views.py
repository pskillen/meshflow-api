from rest_framework import permissions, viewsets

from .models import Constellation, ConstellationUserMembership
from .serializers import ConstellationSerializer


class IsConstellationAdminOrEditor(permissions.BasePermission):
    """
    Permission to only allow admins or editors of a constellation to access its API keys.
    """

    def has_permission(self, request, view):
        # Allow GET requests for listing API keys
        if request.method in permissions.SAFE_METHODS:
            return True

        # For other methods, check if the user is an admin or editor of the constellation
        constellation_id = request.data.get("constellation")
        if not constellation_id:
            return False

        return ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation_id=constellation_id,
            role__in=["admin", "editor"],
        ).exists()

    def has_object_permission(self, request, view, obj):
        # Check if the user is an admin or editor of the constellation
        if hasattr(obj, "constellation"):
            constellation = obj.constellation
        else:
            constellation = obj

        return ConstellationUserMembership.objects.filter(
            user=request.user, constellation=constellation, role__in=["admin", "editor"]
        ).exists()


class ConstellationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for constellations.

    Allows users to create, view, update, and delete constellations
    they have access to.
    """

    serializer_class = ConstellationSerializer
    permission_classes = [permissions.IsAuthenticated, IsConstellationAdminOrEditor]

    def get_queryset(self):
        """
        Filter constellations to only show those the user is a member of.
        """
        user = self.request.user

        # Get the constellations the user is a member of
        constellation_ids = ConstellationUserMembership.objects.filter(
            user=user
        ).values_list("constellation_id", flat=True)

        # Return those constellations
        return Constellation.objects.filter(id__in=constellation_ids)

    def perform_create(self, serializer):
        """
        Create a new constellation and add the user as an admin.
        """
        constellation = serializer.save(created_by=self.request.user)

        # Add the user as an admin of the constellation
        ConstellationUserMembership.objects.create(
            user=self.request.user, constellation=constellation, role="admin"
        )
