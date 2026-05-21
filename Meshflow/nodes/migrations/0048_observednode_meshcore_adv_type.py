from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0047_managednode_mc_pubkey"),
    ]

    operations = [
        migrations.AddField(
            model_name="observednode",
            name="meshcore_adv_type",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="MeshCore ADVERT adv_type (0=none, 1=chat, 2=repeater, 3=room, 4=sensor); null when unknown.",
                null=True,
            ),
        ),
    ]
