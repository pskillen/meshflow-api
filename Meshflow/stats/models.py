"""Models for stored stats snapshots."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class StatsSnapshot(models.Model):
    """Stored snapshot of a stat at a point in time."""

    recorded_at = models.DateTimeField(db_index=True)
    stat_type = models.CharField(max_length=20, db_index=True)
    constellation = models.ForeignKey(
        "constellations.Constellation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stats_snapshots",
    )
    value = models.JSONField()
    run_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("Stats snapshot")
        verbose_name_plural = _("Stats snapshots")
        indexes = [
            models.Index(fields=["recorded_at", "stat_type"]),
            models.Index(fields=["stat_type", "constellation", "recorded_at"]),
        ]
        ordering = ["-recorded_at"]

    def __str__(self):
        scope = f"constellation={self.constellation_id}" if self.constellation_id else "global"
        return f"{self.stat_type} @ {self.recorded_at} ({scope})"
