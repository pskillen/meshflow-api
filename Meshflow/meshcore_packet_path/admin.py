from django.contrib import admin

from meshcore_packet_path.models import MeshCorePathEdgeBucket, MeshCorePathSegmentResolution


@admin.register(MeshCorePathSegmentResolution)
class MeshCorePathSegmentResolutionAdmin(admin.ModelAdmin):
    list_display = (
        "segment_hash",
        "hash_size",
        "hash_mode",
        "status",
        "source",
        "observed_node",
        "last_seen_at",
    )
    list_filter = ("status", "hash_size", "hash_mode", "source")
    search_fields = ("segment_hash", "observed_node__long_name")
    readonly_fields = ("id", "first_seen_at")
    date_hierarchy = "last_seen_at"


@admin.register(MeshCorePathEdgeBucket)
class MeshCorePathEdgeBucketAdmin(admin.ModelAdmin):
    list_display = (
        "bucket_start",
        "from_hash",
        "to_hash",
        "observer",
        "packet_count",
        "observation_count",
        "last_seen_at",
    )
    list_filter = ("bucket_size", "from_kind", "to_kind", "constellation")
    search_fields = ("from_hash", "to_hash")
    date_hierarchy = "bucket_start"
