"""Migration helpers for the ``packets`` app (kept outside ``migrations/``).

Django loads every ``*.py`` in ``migrations/`` as a migration module; helper code
must live elsewhere.
"""

from django.db.migrations.operations.base import Operation
from django.db.migrations.state import get_references


class RenameMeshtasticRawPacketMtiState(Operation):
    """Rename ``RawPacket`` → ``MtRawPacket`` in migration state in one step.

    Django's built-in ``RenameModel`` + ``RenameField`` on MTI ``*_ptr`` fields
    fails during ``state_forwards`` (FieldError / InvalidBasesError) on MTI
    children. This operation mirrors ``ProjectState.rename_model`` but also
    renames each child's parent-link field and updates ``ModelState.bases``
    before any model reload — see Django #26488 / #28243.

    Pair with ``SeparateDatabaseAndState``: use standard ``RenameModel`` /
    ``RenameField`` / ``AlterModelTable`` / ``RenameIndex`` in
    ``database_operations`` (applied to a clone of the pre-migration state) so
    the physical schema matches this state transition.
    """

    reduces_to_sql = False
    reversible = True
    atomic = True

    _OLD_PARENT = "RawPacket"
    _NEW_PARENT = "MtRawPacket"
    _OLD_PTR = "rawpacket_ptr"
    _NEW_PTR = "mtrawpacket_ptr"
    _NEW_DB_TABLE = "packets_mt_raw_packet"

    _CHILD_MODELS_LOWER = (
        "airqualitymetricspacket",
        "devicemetricspacket",
        "environmentmetricspacket",
        "healthmetricspacket",
        "hostmetricspacket",
        "localstatspacket",
        "messagepacket",
        "nodeinfopacket",
        "positionpacket",
        "powermetricspacket",
        "trafficmanagementstatspacket",
        "traceroutepacket",
    )

    def state_forwards(self, app_label, state):
        self._apply(app_label, state, forward=True)

    def state_backwards(self, app_label, state):
        self._apply(app_label, state, forward=False)

    def _apply(self, app_label, state, *, forward):
        if forward:
            old_lower, new_lower = self._OLD_PARENT.lower(), self._NEW_PARENT.lower()
            new_name = self._NEW_PARENT
            old_ptr, new_ptr = self._OLD_PTR, self._NEW_PTR
            new_base = f"{app_label}.{new_lower}"
            db_table_opt = self._NEW_DB_TABLE
        else:
            old_lower, new_lower = self._NEW_PARENT.lower(), self._OLD_PARENT.lower()
            new_name = self._OLD_PARENT
            old_ptr, new_ptr = self._NEW_PTR, self._OLD_PTR
            new_base = f"{app_label}.{new_lower}"
            db_table_opt = None

        renamed_model = state.models[app_label, old_lower].clone()
        renamed_model.name = new_name
        if forward:
            renamed_model.options = {**renamed_model.options, "db_table": db_table_opt}
        else:
            opts = {**renamed_model.options}
            opts.pop("db_table", None)
            renamed_model.options = opts

        state.models[app_label, new_lower] = renamed_model

        old_model_tuple = (app_label, old_lower)
        new_remote_model = f"{app_label}.{new_name}"
        to_reload = set()
        for model_state, fname, field, reference in get_references(state, old_model_tuple):
            changed_field = None
            if reference.to:
                changed_field = field.clone()
                changed_field.remote_field.model = new_remote_model
            if reference.through:
                if changed_field is None:
                    changed_field = field.clone()
                changed_field.remote_field.through = new_remote_model
            if changed_field:
                model_state.fields[fname] = changed_field
                to_reload.add((model_state.app_label, model_state.name_lower))

        for child in self._CHILD_MODELS_LOWER:
            ms = state.models[app_label, child]
            if old_ptr not in ms.fields:
                continue
            field = ms.fields.pop(old_ptr)
            ms.fields[new_ptr] = field.clone()
            ms.bases = (new_base,)

        if state._relations is not None:
            old_name_key = (app_label, old_lower)
            new_name_key = (app_label, new_lower)
            if old_name_key in state._relations:
                state._relations[new_name_key] = state._relations.pop(old_name_key)
            for model_relations in state._relations.values():
                if old_name_key in model_relations:
                    model_relations[new_name_key] = model_relations.pop(old_name_key)

        state.reload_models(to_reload, delay=True)
        state.remove_model(app_label, old_lower)
        state.reload_model(app_label, new_lower, delay=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return "Rename Meshtastic RawPacket MTI parent state to MtRawPacket"


def packets_0017_separate_database_forwards(apps, schema_editor):
    _packets_0017_physical_schema(schema_editor, forward=True)


def packets_0017_separate_database_backwards(apps, schema_editor):
    _packets_0017_physical_schema(schema_editor, forward=False)


def _packets_0017_physical_schema(schema_editor, *, forward):
    """Apply packets.0017 DDL without going through ``RenameModel`` migration state.

    ``SeparateDatabaseAndState``'s inner ``RenameModel`` clone still becomes
    temporarily unrenderable during ``database_forwards`` (StateApps renders all
    models). A single ``RunPython`` avoids that.
    """

    connection = schema_editor.connection
    ops = connection.ops
    qn = ops.quote_name

    child_tables = (
        "packets_airqualitymetricspacket",
        "packets_devicemetricspacket",
        "packets_environmentmetricspacket",
        "packets_healthmetricspacket",
        "packets_hostmetricspacket",
        "packets_localstatspacket",
        "packets_messagepacket",
        "packets_nodeinfopacket",
        "packets_positionpacket",
        "packets_powermetricspacket",
        "packets_trafficmanagementstatspacket",
        "packets_traceroutepacket",
    )
    if forward:
        parent_from, parent_to = "packets_rawpacket", "packets_mt_raw_packet"
        ptr_from, ptr_to = "rawpacket_ptr_id", "mtrawpacket_ptr_id"
        index_pairs = (
            ("packets_raw_packet__cc40c7_idx", "packets_mt__packet__aba474_idx"),
            ("packets_raw_from_in_3cd2a4_idx", "packets_mt__from_in_e6f943_idx"),
            ("packets_raw_from_in_81757d_idx", "packets_mt__from_in_d78106_idx"),
            ("packets_raw_to_int_52668e_idx", "packets_mt__to_int_d08bdd_idx"),
        )
    else:
        parent_from, parent_to = "packets_mt_raw_packet", "packets_rawpacket"
        ptr_from, ptr_to = "mtrawpacket_ptr_id", "rawpacket_ptr_id"
        index_pairs = tuple(
            (new, old)
            for old, new in (
                ("packets_raw_packet__cc40c7_idx", "packets_mt__packet__aba474_idx"),
                ("packets_raw_from_in_3cd2a4_idx", "packets_mt__from_in_e6f943_idx"),
                ("packets_raw_from_in_81757d_idx", "packets_mt__from_in_d78106_idx"),
                ("packets_raw_to_int_52668e_idx", "packets_mt__to_int_d08bdd_idx"),
            )
        )

    def _rename_child_ptr_columns():
        for table in child_tables:
            cursor.execute("ALTER TABLE %s RENAME COLUMN %s TO %s" % (qn(table), qn(ptr_from), qn(ptr_to)))

    def _rename_parent_table():
        cursor.execute("ALTER TABLE %s RENAME TO %s" % (qn(parent_from), qn(parent_to)))

    def _rename_parent_indexes_pg():
        for old_idx, new_idx in index_pairs:
            cursor.execute("ALTER INDEX %s RENAME TO %s" % (qn(old_idx), qn(new_idx)))

    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            if forward:
                _rename_child_ptr_columns()
                _rename_parent_table()
                _rename_parent_indexes_pg()
            else:
                _rename_parent_indexes_pg()
                _rename_parent_table()
                _rename_child_ptr_columns()
        elif connection.vendor == "sqlite":
            if forward:
                _rename_child_ptr_columns()
                _rename_parent_table()
            else:
                _rename_parent_table()
                _rename_child_ptr_columns()
            # SQLite: physical index names may stay on the old ``packets_raw_*``
            # pattern while migration state uses ``packets_mt__*`` names; Django
            # does not require matching physical names for ORM queries.
        else:
            raise NotImplementedError(
                "packets.0017 MTI physical rename unsupported for connection %r" % (connection.vendor,)
            )
