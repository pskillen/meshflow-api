# Generated manually for mesh monitoring config + battery state

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def forwards_copy_offline_after_to_config(apps, schema_editor):
    NodePresence = apps.get_model("mesh_monitoring", "NodePresence")
    NodeMonitoringConfig = apps.get_model("mesh_monitoring", "NodeMonitoringConfig")
    for presence in NodePresence.objects.all().only("observed_node_id", "offline_after"):
        NodeMonitoringConfig.objects.update_or_create(
            observed_node_id=presence.observed_node_id,
            defaults={
                "last_heard_offline_after_seconds": presence.offline_after,
            },
        )


def forwards_sync_watch_offline_flags(apps, schema_editor):
    NodeWatch = apps.get_model("mesh_monitoring", "NodeWatch")
    from django.db.models import F

    NodeWatch.objects.update(offline_notifications_enabled=F("enabled"))


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mesh_monitoring", "0006_move_offline_after_to_node_presence"),
        ("nodes", "0033_managednode_deleted_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="NodeMonitoringConfig",
            fields=[
                (
                    "observed_node",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="monitoring_config",
                        serialize=False,
                        to="nodes.observednode",
                    ),
                ),
                (
                    "last_heard_offline_after_seconds",
                    models.PositiveIntegerField(
                        default=21600,
                        help_text="Seconds since last_heard before verification may start.",
                    ),
                ),
                ("battery_alert_enabled", models.BooleanField(default=False)),
                (
                    "battery_alert_threshold_percent",
                    models.PositiveSmallIntegerField(
                        default=50,
                        validators=[
                            django.core.validators.MinValueValidator(5),
                            django.core.validators.MaxValueValidator(80),
                        ],
                    ),
                ),
                (
                    "battery_alert_report_count",
                    models.PositiveSmallIntegerField(
                        default=2,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Node monitoring config",
                "verbose_name_plural": "Node monitoring configs",
            },
        ),
        migrations.AddField(
            model_name="nodewatch",
            name="offline_notifications_enabled",
            field=models.BooleanField(
                default=True,
                help_text="When enabled and watch is enabled, receive offline / verification Discord notifications.",
            ),
        ),
        migrations.AddField(
            model_name="nodewatch",
            name="battery_notifications_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When enabled and watch is enabled, receive low-battery Discord notifications.",
            ),
        ),
        migrations.RunPython(forwards_sync_watch_offline_flags, backwards_noop),
        migrations.AddField(
            model_name="nodepresence",
            name="battery_below_threshold_report_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Consecutive device-metric reports below the configured battery threshold.",
            ),
        ),
        migrations.AddField(
            model_name="nodepresence",
            name="battery_alerting_since",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nodepresence",
            name="battery_alert_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nodepresence",
            name="last_battery_alert_notify_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nodepresence",
            name="last_battery_recovered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(forwards_copy_offline_after_to_config, backwards_noop),
        migrations.RemoveField(
            model_name="nodepresence",
            name="offline_after",
        ),
    ]
