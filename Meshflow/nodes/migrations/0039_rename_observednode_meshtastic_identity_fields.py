# SP-04: Meshtastic identity fields on ObservedNode

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0038_alter_nodelateststatus_inferred_max_hops_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="observednode",
            old_name="hw_model",
            new_name="meshtastic_hw_model",
        ),
        migrations.RenameField(
            model_name="observednode",
            old_name="public_key",
            new_name="meshtastic_public_key",
        ),
        migrations.RenameField(
            model_name="observednode",
            old_name="role",
            new_name="meshtastic_role",
        ),
        migrations.RenameField(
            model_name="observednode",
            old_name="is_licensed",
            new_name="meshtastic_is_licensed",
        ),
        migrations.RenameField(
            model_name="observednode",
            old_name="is_unmessagable",
            new_name="meshtastic_is_unmessagable",
        ),
    ]
