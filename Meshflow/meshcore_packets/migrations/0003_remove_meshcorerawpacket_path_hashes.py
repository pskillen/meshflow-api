from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("meshcore_packets", "0002_rename_meshcore_raw_prefix_hash_idx_meshcore_pa_from_pu_8e7820_idx_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="meshcorerawpacket",
            name="path_hashes",
        ),
    ]
