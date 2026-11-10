"""Tests for the dedupe_observed_nodes command and merge_duplicate_meshtastic_nodes (#480 part 1)."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.utils import timezone

import pytest

from common.protocol import Protocol
from mesh_monitoring.models import NodeWatch
from nodes.models import NodeLatestStatus, NodeOwnerClaim, ObservedNode, ObservedNodeIdentityLink, Position
from nodes.services.observed_node_merge import HANDLED_RELATIONS, current_relations, merge_duplicate_meshtastic_nodes

pytest_plugins = ["packets.tests.conftest"]

NODE = 0x1A2B3C4D
OTHER_NODE = 0x2B3C4D5E
KEY_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"


@pytest.fixture(autouse=True)
def allow_duplicate_rows(db):
    """Duplicates are what these tests merge, and the unique index now forbids them: drop it for the test.

    The test's transaction rolls the drop back, so other tests still see the index.
    """
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX nodes_observednode_mt_node_id_unique")


def _make(node_id=NODE, *, age_days, heard_days=None, **fields):
    """A Meshtastic ObservedNode created ``age_days`` ago, last heard ``heard_days`` ago (None = never)."""
    now = timezone.now()
    fields.setdefault("long_name", "Unknown Node !1a2b3c4d")
    fields.setdefault("short_name", "3c4d")
    node = ObservedNode.objects.create(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id, **fields)
    ObservedNode.objects.filter(pk=node.pk).update(
        created_at=now - timedelta(days=age_days),
        last_heard=None if heard_days is None else now - timedelta(days=heard_days),
    )
    node.refresh_from_db()
    return node


def _watch(**fields):
    # bulk_create skips NodeWatch.clean(), which only lets users watch claimed or infrastructure nodes.
    NodeWatch.objects.bulk_create([NodeWatch(**fields)])


def _run(*args):
    out = StringIO()
    call_command("dedupe_observed_nodes", *args, stdout=out)
    return out.getvalue()


def _rows(node_id=NODE):
    return ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id)


@pytest.mark.django_db
def test_relation_coverage_is_pinned():
    """A new relation to ObservedNode must be looked at by whoever adds it, then listed in HANDLED_RELATIONS."""
    assert current_relations() == set(HANDLED_RELATIONS)


@pytest.mark.django_db
def test_merge_picks_oldest_keeper_best_name_and_max_last_heard():
    keeper = _make(age_days=10, heard_days=5)  # oldest, placeholder names
    newer = _make(age_days=5, heard_days=1, long_name="Real Name", short_name="REAL", meshtastic_hw_model="TBEAM")
    middle = _make(age_days=7, heard_days=3, long_name="Older Real", short_name="OLDR")

    report = merge_duplicate_meshtastic_nodes()

    assert report.sets_found == 1 and report.rows_merged == 2
    row = _rows().get()
    assert row.pk == keeper.pk
    assert row.long_name == "Real Name" and row.short_name == "REAL"  # from the most recently heard row
    assert row.last_heard == newer.last_heard
    assert row.meshtastic_hw_model == "TBEAM"  # filled because the keeper's was blank
    assert not ObservedNode.objects.filter(pk=middle.pk).exists()


@pytest.mark.django_db
def test_merge_keeps_keeper_identity_fields_and_names_when_only_placeholders_elsewhere():
    keeper = _make(
        age_days=10,
        heard_days=5,
        long_name="Keeper Name",
        short_name="KEEP",
        meshtastic_hw_model="HELTEC",
        mac_addr="aa:aa:aa:aa:aa:aa",
        meshtastic_role=2,
    )
    _make(
        age_days=5,
        heard_days=1,
        meshtastic_hw_model="TBEAM",
        mac_addr="bb:bb:bb:bb:bb:bb",
        meshtastic_role=1,
        meshtastic_public_key="k",
        meshtastic_public_key_hex=KEY_HEX,
        meshtastic_key_node_id=0x4396524C,
    )

    merge_duplicate_meshtastic_nodes()

    row = _rows().get()
    assert row.pk == keeper.pk
    assert (row.long_name, row.short_name) == ("Keeper Name", "KEEP")  # the other row only has placeholders
    assert row.meshtastic_hw_model == "HELTEC" and row.mac_addr == "aa:aa:aa:aa:aa:aa" and row.meshtastic_role == 2
    assert row.meshtastic_public_key_hex == KEY_HEX and row.meshtastic_key_node_id == 0x4396524C  # filled


@pytest.mark.django_db
def test_merge_fills_a_blank_inferred_firmware_from_another_row():
    keeper = _make(age_days=10, heard_days=5)
    _make(
        age_days=5,
        heard_days=1,
        inferred_firmware="2.8",
        inferred_firmware_basis="key_identity",
        inferred_firmware_at=timezone.now(),
    )

    merge_duplicate_meshtastic_nodes()

    row = _rows().get()
    assert row.pk == keeper.pk
    assert (row.inferred_firmware, row.inferred_firmware_basis) == ("2.8", "key_identity")
    assert row.inferred_firmware_at is not None


@pytest.mark.django_db
def test_merge_keeps_the_keepers_inferred_firmware():
    _make(age_days=10, heard_days=5, inferred_firmware="2.7", inferred_firmware_basis="key_identity")
    _make(age_days=5, heard_days=1, inferred_firmware="2.8", inferred_firmware_basis="predicted_id")

    merge_duplicate_meshtastic_nodes()

    row = _rows().get()
    assert (row.inferred_firmware, row.inferred_firmware_basis) == ("2.7", "key_identity")


@pytest.mark.django_db
def test_merge_moves_fk_and_one_to_one_rows_to_keeper_without_integrity_errors(create_user):
    user = create_user()
    keeper = _make(age_days=10, heard_days=5)
    loser = _make(age_days=5, heard_days=1)

    Position.objects.create(node=loser, latitude=1.0, longitude=2.0)
    Position.objects.create(node=keeper, latitude=3.0, longitude=4.0)
    NodeOwnerClaim.objects.create(node=loser, user=user, claim_key="abc")
    # Same (user, node) watch on both: the keeper's wins, no IntegrityError.
    _watch(user=user, observed_node=keeper, enabled=True)
    _watch(user=user, observed_node=loser, enabled=False)
    other_user = create_user()
    _watch(user=other_user, observed_node=loser)
    # A NodeLatestStatus on each side: the keeper's stays.
    NodeLatestStatus.objects.create(node=keeper, latitude=10.0)
    NodeLatestStatus.objects.create(node=loser, latitude=20.0)

    report = merge_duplicate_meshtastic_nodes()

    assert Position.objects.filter(node=keeper).count() == 2
    assert NodeWatch.objects.filter(observed_node=keeper).count() == 2
    assert NodeWatch.objects.get(user=user, observed_node=keeper).enabled is True
    assert NodeLatestStatus.objects.get(node=keeper).latitude == 10.0
    assert NodeLatestStatus.objects.count() == 1
    assert NodeOwnerClaim.objects.get().node_id == keeper.pk
    assert report.moved["nodes.Position.node"] == 1
    assert report.moved["mesh_monitoring.NodeWatch.observed_node"] == 1
    assert report.dropped["mesh_monitoring.NodeWatch.observed_node"] == 1
    assert report.dropped["nodes.NodeLatestStatus.node"] == 1


@pytest.mark.django_db
def test_one_to_one_moves_across_when_keeper_has_none():
    keeper = _make(age_days=10, heard_days=5)
    old_loser = _make(age_days=7, heard_days=4)
    new_loser = _make(age_days=5, heard_days=1)
    NodeLatestStatus.objects.create(node=old_loser, latitude=1.0)
    NodeLatestStatus.objects.create(node=new_loser, latitude=2.0)

    report = merge_duplicate_meshtastic_nodes()

    assert NodeLatestStatus.objects.get(node=keeper).latitude == 2.0  # the most recently heard duplicate's row
    assert NodeLatestStatus.objects.count() == 1
    assert report.moved["nodes.NodeLatestStatus.node"] == 1
    assert report.dropped["nodes.NodeLatestStatus.node"] == 1


@pytest.mark.django_db
def test_dry_run_writes_nothing_and_reports_the_same_counts_as_the_real_run(create_user):
    user = create_user()
    keeper = _make(age_days=10, heard_days=5)
    loser = _make(age_days=5, heard_days=1, long_name="Real Name", short_name="REAL")
    Position.objects.create(node=loser, latitude=1.0, longitude=2.0)
    _watch(user=user, observed_node=keeper)
    _watch(user=user, observed_node=loser)
    NodeLatestStatus.objects.create(node=loser, latitude=2.0)
    # A second duplicate set.
    _make(OTHER_NODE, age_days=3, heard_days=2, long_name="Unknown Node !2b3c4d5e", short_name="4d5e")
    _make(OTHER_NODE, age_days=2, heard_days=1, long_name="Unknown Node !2b3c4d5e", short_name="4d5e")

    dry_out = _run("--dry-run")
    assert ObservedNode.objects.count() == 4
    assert Position.objects.get().node_id == loser.pk
    assert NodeWatch.objects.count() == 2
    assert NodeLatestStatus.objects.get().node_id == loser.pk
    keeper.refresh_from_db()
    assert keeper.long_name == "Unknown Node !1a2b3c4d"

    real_out = _run()
    assert ObservedNode.objects.count() == 2
    assert dry_out.replace("[dry-run] ", "") == real_out
    assert "Duplicate sets found: 2, merged: 2, rows merged away: 2, conflicts skipped: 0" in real_out

    # Idempotent: a re-run finds nothing.
    again = _run()
    assert "Duplicate sets found: 0, merged: 0, rows merged away: 0, conflicts skipped: 0" in again
    assert ObservedNode.objects.count() == 2


@pytest.mark.django_db
def test_different_owners_are_skipped_and_reported(create_user):
    a, b = create_user(), create_user()
    _make(age_days=10, heard_days=5, claimed_by=a)
    _make(age_days=5, heard_days=1, claimed_by=b)

    out = _run()

    assert _rows().count() == 2
    assert "conflicts skipped: 1" in out
    assert "!1a2b3c4d" in out


@pytest.mark.django_db
def test_claimed_by_is_filled_from_another_row_when_keeper_has_none(create_user):
    owner = create_user()
    keeper = _make(age_days=10, heard_days=5)
    _make(age_days=5, heard_days=1, claimed_by=owner)

    merge_duplicate_meshtastic_nodes()

    keeper.refresh_from_db()
    assert keeper.claimed_by_id == owner.pk
    assert _rows().count() == 1


@pytest.mark.django_db
def test_same_owner_on_both_rows_is_not_a_conflict(create_user):
    owner = create_user()
    _make(age_days=10, heard_days=5, claimed_by=owner)
    _make(age_days=5, heard_days=1, claimed_by=owner)

    merge_duplicate_meshtastic_nodes()

    assert _rows().count() == 1


@pytest.mark.django_db
def test_meshcore_rows_and_unique_numbers_are_untouched():
    _make(age_days=5, heard_days=1)
    ObservedNode.objects.create(protocol=Protocol.MESHCORE, mc_pubkey="ab" * 32, long_name="MC", short_name="MC")
    ObservedNode.objects.create(protocol=Protocol.MESHCORE, mc_pubkey="cd" * 32, long_name="MC2", short_name="MC2")

    report = merge_duplicate_meshtastic_nodes()

    assert report.sets_found == 0
    assert ObservedNode.objects.count() == 3


# --- identity links (ID-2) --------------------------------------------------------------------------------------

Link = ObservedNodeIdentityLink
State = Link.State


def _link(old, new, state=State.AUTO, evidence=Link.Evidence.PUBLIC_KEY):
    return Link.objects.create(old_node=old, new_node=new, state=state, evidence=evidence, confidence="strong")


def _pair():
    """A keeper/loser pair sharing one node number (keeper is the older row)."""
    keeper = _make(age_days=10, heard_days=5)
    loser = _make(age_days=5, heard_days=1)
    return keeper, loser


@pytest.mark.django_db
def test_merge_repoints_links_on_both_sides_to_the_keeper():
    keeper, loser = _pair()
    before = _make(OTHER_NODE, age_days=3, heard_days=1)
    after = _make(0x3C4D5E6F, age_days=3, heard_days=1)
    _link(before, loser)  # loser as the new side
    _link(loser, after, evidence=Link.Evidence.MAC, state=State.SUGGESTED)  # loser as the old side

    report = merge_duplicate_meshtastic_nodes()

    assert report.moved["nodes.ObservedNodeIdentityLink.new_node"] == 1
    assert report.moved["nodes.ObservedNodeIdentityLink.old_node"] == 1
    assert Link.objects.get(old_node=before).new_node_id == keeper.pk
    assert Link.objects.get(new_node=after).old_node_id == keeper.pk


@pytest.mark.django_db
def test_merge_drops_a_losers_link_that_duplicates_the_keepers_pair():
    keeper, loser = _pair()
    other = _make(OTHER_NODE, age_days=3, heard_days=1)
    kept = _link(keeper, other)
    _link(loser, other, state=State.SUGGESTED, evidence=Link.Evidence.MAC)

    report = merge_duplicate_meshtastic_nodes()

    assert report.dropped["nodes.ObservedNodeIdentityLink.old_node"] == 1
    assert list(Link.objects.values_list("pk", flat=True)) == [kept.pk]


@pytest.mark.django_db
def test_merge_drops_a_losers_live_link_when_the_keeper_already_has_a_live_successor():
    keeper, loser = _pair()
    one = _make(OTHER_NODE, age_days=3, heard_days=1)
    two = _make(0x3C4D5E6F, age_days=3, heard_days=1)
    kept = _link(keeper, one)
    _link(loser, two)  # a second live successor of the merged node would break the one-live-successor rule

    merge_duplicate_meshtastic_nodes()

    assert list(Link.objects.values_list("pk", flat=True)) == [kept.pk]


@pytest.mark.django_db
def test_merge_drops_a_link_between_the_keeper_and_the_loser():
    keeper, loser = _pair()
    _link(keeper, loser)  # would become a link from the node to itself

    merge_duplicate_meshtastic_nodes()

    assert not Link.objects.exists()
    assert _rows().count() == 1


@pytest.mark.django_db
def test_merge_keeps_a_confirmed_link_over_a_weaker_clashing_one():
    keeper, loser = _pair()
    other = _make(OTHER_NODE, age_days=3, heard_days=1)
    _link(keeper, other, state=State.SUGGESTED, evidence=Link.Evidence.MAC)
    confirmed = _link(loser, other, state=State.CONFIRMED)

    merge_duplicate_meshtastic_nodes()

    survivor = Link.objects.get()
    assert survivor.pk == confirmed.pk and survivor.state == State.CONFIRMED
    assert survivor.old_node_id == keeper.pk


@pytest.mark.django_db
def test_merge_dry_run_leaves_links_alone():
    keeper, loser = _pair()
    other = _make(OTHER_NODE, age_days=3, heard_days=1)
    link = _link(other, loser)

    merge_duplicate_meshtastic_nodes(dry_run=True)

    link.refresh_from_db()
    assert link.new_node_id == loser.pk
    assert _rows().count() == 2
