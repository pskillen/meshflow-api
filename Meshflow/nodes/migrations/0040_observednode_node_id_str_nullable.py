# #294: allow null before dropping persisted node_id_str

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0039_rename_observednode_meshtastic_identity_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="observednode",
            name="node_id_str",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Display id: !hex8 (Meshtastic) or mc:prefix12 (MeshCore). Deprecated; dropped in #294.",
                max_length=16,
                null=True,
            ),
        ),
    ]
