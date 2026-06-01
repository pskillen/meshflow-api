"""Passive MeshCore packet path evidence (hash chains, segment resolution, edge rollups)."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from constellations.models import Constellation
from nodes.models import ManagedNode, ObservedNode


class SegmentStatus(models.TextChoices):
    UNKNOWN = "unknown", _("Unknown")
    RESOLVED = "resolved", _("Resolved")
    AMBIGUOUS = "ambiguous", _("Ambiguous")
    STALE = "stale", _("Stale")


class EdgeKind(models.TextChoices):
    HASH = "hash", _("Hash")
    NODE = "node", _("Node")
    FEEDER = "feeder", _("Feeder")
    UNKNOWN = "unknown", _("Unknown")


class MeshCorePathSegmentResolution(models.Model):
    """One resolvable path segment identity (hash_mode, hash_size, segment_hash)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    segment_hash = models.CharField(max_length=32, db_index=True)
    hash_size = models.PositiveSmallIntegerField(null=True, blank=True)
    hash_mode = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_node = models.ForeignKey(
        ObservedNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_path_segments",
    )
    status = models.CharField(
        max_length=16,
        choices=SegmentStatus.choices,
        default=SegmentStatus.UNKNOWN,
        db_index=True,
    )
    source = models.CharField(max_length=32, blank=True, default="")
    resolver_version = models.PositiveIntegerField(default=1)
    confidence = models.FloatField(null=True, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hash_mode", "hash_size", "segment_hash"],
                name="meshcore_path_segment_identity_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["-last_seen_at"]),
            models.Index(fields=["status", "-last_seen_at"]),
        ]
        verbose_name = _("MeshCore path segment resolution")
        verbose_name_plural = _("MeshCore path segment resolutions")

    def __str__(self):
        return f"{self.segment_hash} ({self.status})"


class MeshCorePathEdgeBucket(models.Model):
    """Hourly (or other) rollup of passive hash-chain edges."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bucket_start = models.DateTimeField(db_index=True)
    bucket_size = models.CharField(max_length=8, default="1h")
    from_kind = models.CharField(max_length=16, choices=EdgeKind.choices, default=EdgeKind.HASH)
    to_kind = models.CharField(max_length=16, choices=EdgeKind.choices, default=EdgeKind.HASH)
    from_hash = models.CharField(max_length=32, blank=True, default="")
    to_hash = models.CharField(max_length=32, blank=True, default="")
    from_node = models.ForeignKey(
        ObservedNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_path_edges_from",
    )
    to_node = models.ForeignKey(
        ObservedNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_path_edges_to",
    )
    observer = models.ForeignKey(
        ManagedNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_path_edge_buckets",
    )
    constellation = models.ForeignKey(
        Constellation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_path_edge_buckets",
    )
    packet_count = models.PositiveIntegerField(default=0)
    observation_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    avg_snr = models.FloatField(null=True, blank=True)
    min_snr = models.FloatField(null=True, blank=True)
    max_snr = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "bucket_start",
                    "bucket_size",
                    "from_kind",
                    "to_kind",
                    "from_hash",
                    "to_hash",
                    "observer",
                    "constellation",
                ],
                name="meshcore_path_edge_bucket_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=["-bucket_start"]),
            models.Index(fields=["from_hash", "to_hash"]),
        ]
        verbose_name = _("MeshCore path edge bucket")
        verbose_name_plural = _("MeshCore path edge buckets")

    def __str__(self):
        return f"{self.from_hash}->{self.to_hash} @ {self.bucket_start}"
