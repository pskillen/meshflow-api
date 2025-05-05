from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Constellation, ConstellationUserMembership, MessageChannel


class ConstellationAdminForm(forms.ModelForm):
    class Meta:
        model = Constellation
        fields = "__all__"
        widgets = {
            "map_color": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(Constellation)
class ConstellationAdmin(admin.ModelAdmin):
    form = ConstellationAdminForm
    list_display = (
        "name",
        "created_by",
        "get_member_count",
        "get_admin_count",
        "get_node_count",
        "colored_map_color",
    )
    list_filter = ("created_by",)
    search_fields = ("name", "description", "created_by__username", "created_by__email")
    ordering = ("name",)
    readonly_fields = ("created_by",)

    _COLOR_FIELD_TEMPLATE = (
        '<div style="background:{}; width: 100%; height: 24px; border-radius: 4px; '
        'border: 1px solid #ccc; text-align:center; color: {};">'
        "{color}"
        "</div>"
    )

    def get_member_count(self, obj):
        return obj.constellationusermembership_set.count()

    get_member_count.short_description = _("Members")
    get_member_count.admin_order_field = "constellationusermembership__count"

    def get_admin_count(self, obj):
        return obj.constellationusermembership_set.filter(role="admin").count()

    get_admin_count.short_description = _("Admins")

    def get_node_count(self, obj):
        return obj.nodes.count()

    get_node_count.short_description = _("Managed nodes")
    get_node_count.admin_order_field = "nodes__count"

    def colored_map_color(self, obj):
        color = obj.map_color or "#000000"
        # Calculate brightness to choose foreground color
        hex_color = color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join([c * 2 for c in hex_color])
        try:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        except Exception:
            r, g, b = 0, 0, 0
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        fg = "#000" if brightness > 128 else "#fff"
        return format_html(
            self._COLOR_FIELD_TEMPLATE,
            color,
            fg,
            color,
        )

    colored_map_color.short_description = "Map Color"

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
