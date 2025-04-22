from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import MeshtasticNode


@admin.register(MeshtasticNode)
class MeshtasticNodeAdmin(admin.ModelAdmin):
    list_display = (
        "short_name",
        "long_name",
        "node_id_str",
        "constellation",
        "owner",
        "hw_model",
        "sw_version",
    )
    list_filter = (
        "constellation",
        "owner",
        "hw_model",
    )
    search_fields = (
        "short_name",
        "long_name",
        "node_id",
        "mac_addr",
        "hw_model",
        "sw_version",
        "owner__username",
        "owner__email",
    )
    readonly_fields = (
        "internal_id",
        "node_id",
        "node_id_str",
        "mac_addr",
        "public_key",
    )
    fieldsets = (
        (None, {
            "fields": (
                "constellation",
                "owner",
                "short_name",
                "long_name",
            )
        }),
        (_("Hardware Information"), {
            "fields": (
                "hw_model",
                "sw_version",
            )
        }),
        (_("Technical Details"), {
            "fields": (
                "node_id",
                "node_id_str",
                "mac_addr",
                "public_key",
            ),
            "classes": ("collapse",),
        }),
    )

