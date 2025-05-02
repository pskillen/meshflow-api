from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Constellation, ConstellationUserMembership, MessageChannel


@admin.register(Constellation)
class ConstellationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "created_by",
        "get_member_count",
        "get_admin_count",
        "get_node_count",
        "get_api_key_count",
    )
    list_filter = ("created_by",)
    search_fields = ("name", "description", "created_by__username", "created_by__email")
    ordering = ("name",)
    readonly_fields = ("created_by",)

    def get_member_count(self, obj):
        return obj.constellationusermembership_set.count()

    get_member_count.short_description = _("Members")
    get_member_count.admin_order_field = "constellationusermembership__count"

    def get_admin_count(self, obj):
        return obj.constellationusermembership_set.filter(role="admin").count()

    get_admin_count.short_description = _("Admins")

    def get_node_count(self, obj):
        return obj.nodes.count()

    get_node_count.short_description = _("Nodes")
    get_node_count.admin_order_field = "nodes__count"

    def get_api_key_count(self, obj):
        return obj.api_keys.count()

    get_api_key_count.short_description = _("API Keys")
    get_api_key_count.admin_order_field = "api_keys__count"

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ConstellationUserMembership)
class ConstellationUserMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "constellation",
        "role",
        "get_user_email",
        "get_constellation_creator",
    )
    list_filter = ("role", "constellation", "user")
    search_fields = ("user__username", "user__email", "constellation__name")
    ordering = ("constellation__name", "user__username")

    def get_user_email(self, obj):
        return obj.user.email

    get_user_email.short_description = _("User Email")
    get_user_email.admin_order_field = "user__email"

    def get_constellation_creator(self, obj):
        return obj.constellation.created_by.username

    get_constellation_creator.short_description = _("Constellation Creator")
    get_constellation_creator.admin_order_field = "constellation__created_by__username"


@admin.register(MessageChannel)
class MessageChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "constellation")
    list_filter = ("constellation",)
    search_fields = ("name", "id")
    ordering = ("name",)
