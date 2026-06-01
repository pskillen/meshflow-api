# Placeholder dependency anchor between link backfill and finalize

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0012_remove_mc_idx_constraint"),
        ("nodes", "0051_mc_canonical_channels"),
    ]

    operations = []
