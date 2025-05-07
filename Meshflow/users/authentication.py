from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings


class JWTAuthentication(BaseJWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        # Handle None or non-integer user_id gracefully
        if user_id is None or (isinstance(user_id, str) and not user_id.isdigit()):
            raise AuthenticationFailed(
                _("Invalid token: user_id is missing or not a valid integer."), code="user_id_invalid"
            )
        try:
            user = self.user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        if getattr(settings, "SIMPLE_JWT", {}).get("CHECK_REVOKE_TOKEN", False):
            from rest_framework_simplejwt.utils import get_md5_hash_password

            if validated_token.get(
                getattr(settings, "SIMPLE_JWT", {}).get("REVOKE_TOKEN_CLAIM", "")
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(_("The user's password has been changed."), code="password_changed")

        return user
