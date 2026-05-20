from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0041_rename_metrics_meshtastic_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="managednode",
            name="bot_version",
            field=models.CharField(
                blank=True,
                help_text="Last meshflow-bot version reported by this feeder on connect.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="managednode",
            name="bot_version_reported_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When bot_version was last reported by the feeder.",
                null=True,
            ),
        ),
    ]
