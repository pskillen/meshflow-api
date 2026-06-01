# Manual split for #379 — drop index uniqueness before link backfill

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0011_remove_constellationusermembership"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="messagechannel",
            name="messagechannel_mc_idx_constellation_unique",
        ),
    ]
