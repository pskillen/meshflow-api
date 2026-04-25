# Generated manually for meshflow-api#218

from django.db import migrations, models


def forwards_copy_trigger_type(apps, schema_editor):
    AutoTraceRoute = apps.get_model("traceroute", "AutoTraceRoute")
    mapping = {
        "user": 1,
        "external": 2,
        "auto": 3,
        "monitor": 4,
    }
    for row in AutoTraceRoute.objects.all().only("id", "trigger_type"):
        legacy = row.trigger_type
        val = mapping.get(legacy, 3)
        AutoTraceRoute.objects.filter(pk=row.pk).update(trigger_type_int=val)


class Migration(migrations.Migration):

    dependencies = [
        ("traceroute", "0009_add_manual_target_strategy"),
    ]

    operations = [
        migrations.AddField(
            model_name="autotraceroute",
            name="trigger_type_int",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.RunPython(forwards_copy_trigger_type, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="autotraceroute",
            name="trigger_type",
        ),
        migrations.RenameField(
            model_name="autotraceroute",
            old_name="trigger_type_int",
            new_name="trigger_type",
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
                ],
            ),
        ),
    ]
