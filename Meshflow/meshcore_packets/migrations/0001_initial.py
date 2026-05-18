# Generated manually for MeshCore Phase 1

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("constellations", "0006_protocol_fields_messagechannel_constellation"),
        ("nodes", "0036_observednode_mc_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="MeshCoreRawPacket",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "payload_type",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "advert"), (2, "channel_text"), (3, "contact_text"), (99, "raw")],
                        db_index=True,
                    ),
                ),
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("from_pubkey", models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ("from_pubkey_prefix", models.CharField(blank=True, db_index=True, max_length=12, null=True)),
                ("pkt_hash", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("rx_time", models.DateTimeField(db_index=True)),
                ("rx_rssi", models.FloatField(blank=True, null=True)),
                ("rx_snr", models.FloatField(blank=True, null=True)),
                ("route_typename", models.CharField(blank=True, max_length=32, null=True)),
                ("path_hashes", models.JSONField(blank=True, null=True)),
                ("raw_json", models.JSONField()),
                ("first_reported_time", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "observer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meshcore_packets_observed",
                        to="nodes.managednode",
                    ),
                ),
            ],
            options={
                "verbose_name": "MeshCore raw packet",
                "verbose_name_plural": "MeshCore raw packets",
                "db_table": "meshcore_packets_raw",
            },
        ),
        migrations.CreateModel(
            name="MeshCoreTextPacket",
            fields=[
                (
                    "meshcorerawpacket_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="meshcore_packets.meshcorerawpacket",
                    ),
                ),
                ("to_pubkey_prefix", models.CharField(blank=True, max_length=12, null=True)),
                ("text", models.TextField()),
                (
                    "channel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="meshcore_text_packets",
                        to="constellations.messagechannel",
                    ),
                ),
            ],
            options={
                "verbose_name": "MeshCore text packet",
                "verbose_name_plural": "MeshCore text packets",
            },
            bases=("meshcore_packets.meshcorerawpacket",),
        ),
        migrations.CreateModel(
            name="MeshCorePacketObservation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("rx_time", models.DateTimeField()),
                ("rx_rssi", models.FloatField(blank=True, null=True)),
                ("rx_snr", models.FloatField(blank=True, null=True)),
                ("path_hashes", models.JSONField(blank=True, null=True)),
                ("upload_time", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "channel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="meshcore_observations",
                        to="constellations.messagechannel",
                    ),
                ),
                (
                    "observer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meshcore_packet_observations",
                        to="nodes.managednode",
                    ),
                ),
                (
                    "packet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observations",
                        to="meshcore_packets.meshcorerawpacket",
                    ),
                ),
            ],
            options={
                "verbose_name": "MeshCore packet observation",
                "verbose_name_plural": "MeshCore packet observations",
            },
        ),
        migrations.AddIndex(
            model_name="meshcorerawpacket",
            index=models.Index(fields=["from_pubkey_prefix", "pkt_hash"], name="meshcore_raw_prefix_hash_idx"),
        ),
        migrations.AddIndex(
            model_name="meshcorerawpacket",
            index=models.Index(fields=["-rx_time"], name="meshcore_raw_rx_time_idx"),
        ),
        migrations.AddConstraint(
            model_name="meshcorepacketobservation",
            constraint=models.UniqueConstraint(
                fields=("packet", "observer"),
                name="meshcore_obs_packet_observer_unique",
            ),
        ),
    ]
