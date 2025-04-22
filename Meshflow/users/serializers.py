from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for users."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'display_name']
        read_only_fields = ['id']
