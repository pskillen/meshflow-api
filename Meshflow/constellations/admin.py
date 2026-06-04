from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from common.mc_channel_labels import mc_channel_admin_label, mc_channel_type_name
from common.protocol import Protocol

from .models import Constellation, MeshCoreMessageChannel, MessageChannel

_SCOPE_FILTER_NONE = "__none__"
_SCOPE_FILTER_ANY = "__any__"


class MeshCoreRegionScopeFilter(admin.SimpleListFilter):
    """Filter MeshCore channels by region_scope (null, any, or a specific scope)."""

    title = _("Region scope")
    parameter_name = "region_scope"

    def lookups(self, request, model_admin):
        choices = [
            (_SCOPE_FILTER_NONE, _("No scope")),
            (_SCOPE_FILTER_ANY, _("Has scope")),
        ]
        qs = model_admin.get_queryset(request).filter(region_scope__isnull=False)
        scopes = qs.values_list("region_scope", flat=True).distinct().order_by("region_scope")
        choices.extend((scope, scope) for scope in scopes if scope)
        return choices

    def queryset(self, request, queryset):
        if self.value() == _SCOPE_FILTER_NONE:
            return queryset.filter(region_scope__isnull=True)
        if self.value() == _SCOPE_FILTER_ANY:
            return queryset.filter(region_scope__isnull=False)
        if self.value():
            return queryset.filter(region_scope=self.value())
        return queryset


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
        "protocol",
        "created_by",
        "get_node_count",
        "map_color",
        "bot_default_ignore_meshtastic_portnums",
        "bot_default_meshtastic_hop_limit",
    )
    list_filter = (("protocol", admin.ChoicesFieldListFilter), "created_by")
    search_fields = ("name", "description", "created_by__username", "created_by__email")
    ordering = ("name",)
    readonly_fields = ("created_by",)
    fieldsets = (
        (None, {"fields": ("name", "description", "protocol", "created_by", "map_color")}),
        (
            _("Bot setup defaults"),
            {
                "fields": ("bot_default_ignore_meshtastic_portnums", "bot_default_meshtastic_hop_limit"),
                "description": _(
                    "Default env vars for generated docker-compose/.env during onboarding. "
                    "Leave blank to omit from generated config."
                ),
            },
        ),
    )

    _COLOR_FIELD_TEMPLATE = (
        '<div style="background:{}; width: 100%; height: 24px; border-radius: 4px; '
        'border: 1px solid #ccc; text-align:center; color: {};">'
        "{map_color}"
        "</div>"
    )

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


@admin.register(MessageChannel)
class MessageChannelAdmin(admin.ModelAdmin):
    """Meshtastic and legacy rows; MeshCore operators should use MeshCore channels."""

    list_display = ("id", "name", "protocol", "constellation")
    list_filter = (
        ("protocol", admin.ChoicesFieldListFilter),
        "constellation",
    )
    search_fields = ("name", "id", "constellation__name")
    ordering = ("constellation__name", "name")
    list_select_related = ("constellation",)


@admin.register(MeshCoreMessageChannel)
class MeshCoreMessageChannelAdmin(admin.ModelAdmin):
    """Constellation MC channel catalog (device slots). Push to radio from Managed node admin."""

    list_display = (
        "admin_label",
        "mc_channel_type_display",
        "region_scope_display",
        "constellation",
        "id",
    )
    list_filter = (
        ("mc_channel_type", admin.ChoicesFieldListFilter),
        MeshCoreRegionScopeFilter,
        "constellation",
    )
    search_fields = ("name", "region_scope", "constellation__name")
    ordering = ("constellation__name", "name")
    list_select_related = ("constellation",)
    fieldsets = (
        (None, {"fields": ("constellation",)}),
        (
            _("Channel"),
            {
                "fields": ("name", "mc_channel_type", "region_scope"),
                "description": _(
                    "PUBLIC channels use a plain name. HASHTAG channels store the tag in name "
                    "(no leading #); lists show #prefix. region_scope is optional (null = legacy scope)."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(protocol=Protocol.MESHCORE)

    def save_model(self, request, obj, form, change):
        obj.protocol = Protocol.MESHCORE
        super().save_model(request, obj, form, change)

    @admin.display(description=_("Label"), ordering="name")
    def admin_label(self, obj):
        return mc_channel_admin_label(obj)

    @admin.display(description=_("Type"), ordering="mc_channel_type")
    def mc_channel_type_display(self, obj):
        return mc_channel_type_name(obj)

    @admin.display(description=_("Scope"), ordering="region_scope")
    def region_scope_display(self, obj):
        return obj.region_scope or "—"
