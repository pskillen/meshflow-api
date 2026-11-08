from django.db import migrations, models


class Migration(migrations.Migration):

    # Depends on 0053 because nodes 0054 (#484) is not on main yet. Whichever of the two merges second renumbers
    # and points its dependency at the other.
    dependencies = [
        ('nodes', '0053_meshtastic_identity_evidence'),
    ]

    operations = [
        migrations.AddField(
            model_name='nodelateststatus',
            name='meshtastic_inferred_max_hops_at',
            field=models.DateTimeField(blank=True, help_text='When meshtastic_inferred_max_hops was last written.', null=True),
        ),
        migrations.AddField(
            model_name='nodelateststatus',
            name='meshtastic_inferred_max_hops_source',
            field=models.CharField(blank=True, help_text='Port name (e.g. TEXT_MESSAGE_APP) of the packet that set meshtastic_inferred_max_hops.', max_length=50, null=True),
        ),
    ]
