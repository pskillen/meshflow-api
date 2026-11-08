from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('packets', '0019_generic_packet_rx_time_estimated'),
    ]

    operations = [
        migrations.AddField(
            model_name='packetobservation',
            name='bitfield',
            field=models.PositiveIntegerField(null=True),
        ),
    ]
