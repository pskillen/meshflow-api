from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "display_name",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = (
        "is_staff",
        "is_active",
        "is_superuser",
        "date_joined",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "display_name",
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {
            "fields": (
                "display_name",
                "first_name",
                "last_name",
                "email",
            )
        }),
        (_("Permissions"), {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
            "classes": ("collapse",),
        }),
        (_("Important dates"), {
            "fields": ("last_login", "date_joined"),
            "classes": ("collapse",),
        }),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "password1",
                "password2",
                "display_name",
                "email",
            ),
        }),
    )
    ordering = ("username",)
