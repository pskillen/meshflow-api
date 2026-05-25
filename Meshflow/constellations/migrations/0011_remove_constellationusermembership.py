from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0010_meshcore_message_channel_proxy"),
        ("users", "0003_feeder_group"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ConstellationUserMembership",
        ),
    ]
