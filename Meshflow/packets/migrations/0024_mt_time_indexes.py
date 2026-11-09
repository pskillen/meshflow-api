"""Index the time columns the online-nodes snapshots range-scan (MtRawPacket, PacketObservation).

Both tables are large in production, so on PostgreSQL the indexes are built with CREATE INDEX
CONCURRENTLY, which does not block writes while it builds. That cannot run inside a transaction, hence
`atomic = False`. Other databases (the SQLite test database) get a plain, transactional index build.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class AddIndexConcurrentlyOnPostgres(AddIndexConcurrently):
    """AddIndexConcurrently where the database supports it, an ordinary AddIndex elsewhere."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            super().database_forwards(app_label, schema_editor, from_state, to_state)
        else:
            migrations.AddIndex.database_forwards(self, app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            super().database_backwards(app_label, schema_editor, from_state, to_state)
        else:
            migrations.AddIndex.database_backwards(self, app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("packets", "0023_observation_transport"),
    ]

    operations = [
        AddIndexConcurrentlyOnPostgres(
            model_name="mtrawpacket",
            index=models.Index(fields=["first_reported_time"], name="packets_mt_first_rep_idx"),
        ),
        AddIndexConcurrentlyOnPostgres(
            model_name="packetobservation",
            index=models.Index(fields=["rx_time"], name="packets_po_rx_time_idx"),
        ),
    ]
