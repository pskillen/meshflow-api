# New-node baseline traceroute trigger type + partial unique constraint (meshflow-api#236)

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("traceroute", "0011_traceroute_dispatch_queue"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="autotraceroute",
            new_name="traceroute__status_6682f8_idx",
            old_name="traceroute__status_b7e6f0_idx",
        ),
        migrations.AlterField(
            model_name="autotraceroute",
            name="earliest_send_at",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
                help_text="Not before this time: dispatch to source node (per-feeder spacing in the dispatcher)",
            ),
        ),
        migrations.AlterField(
            model_name="autotraceroute",
            name="trigger_type",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "User"),
                    (2, "External"),
                    (3, "Monitoring"),
                    (4, "Node Watch"),
                    (5, "DX Watch"),
                    (6, "New node baseline"),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="autotraceroute",
            constraint=models.UniqueConstraint(
                condition=models.Q(("trigger_type", 6)),
                fields=("target_node",),
                name="traceroute_autotraceroute_new_node_baseline_unique_target",
            ),
        ),
    ]
