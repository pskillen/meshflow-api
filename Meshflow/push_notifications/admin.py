from django.contrib import admin

from .models import DiscordNotificationAudit


@admin.register(DiscordNotificationAudit)
class DiscordNotificationAuditAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "feature",
        "kind",
        "status",
        "discord_recipient_id",
        "message_preview",
    )
    list_filter = ("feature", "kind", "status", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "discord_recipient_id",
        "reason",
        "message_preview",
        "related_object_id",
    )
    readonly_fields = (
        "created_at",
        "attempted_at",
        "sent_at",
        "user",
        "feature",
        "kind",
        "status",
        "discord_recipient_id",
        "reason",
        "message_preview",
        "related_app_label",
        "related_model_name",
        "related_object_id",
        "related_context",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
