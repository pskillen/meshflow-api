from django.contrib import admin

from .models import M2MApiKey, M2MApiKeyUsageDaily


class UsageInline(admin.TabularInline):
    model = M2MApiKeyUsageDaily
    extra = 0
    readonly_fields = ("date", "request_count")


@admin.register(M2MApiKey)
class M2MApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "owner", "rate_tier", "revoked_at", "created_at")
    list_filter = ("rate_tier", "revoked_at")
    search_fields = ("name", "prefix", "owner__username")
    readonly_fields = ("prefix", "hashed_key", "created_at", "last_used_at")
    inlines = [UsageInline]
    actions = ["revoke_keys"]

    @admin.action(description="Revoke selected keys")
    def revoke_keys(self, request, queryset):
        from django.utils import timezone

        queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now(), revoked_reason="staff_revoked")
