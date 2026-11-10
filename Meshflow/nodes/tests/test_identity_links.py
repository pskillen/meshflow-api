"""Identity links between the Meshtastic numbers of one radio (ID-2): nodes.services.identity_links."""

import logging
from io import StringIO
from unittest import mock

from django.contrib import admin as django_admin
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from common.meshtastic_identity import identity_fields, key_node_id, mac_node_number, normalise_pubkey
from common.protocol import Protocol
from nodes.models import ManagedNodeIdentityEvent, ObservedNode, ObservedNodeIdentityLink
from nodes.services import identity_links
from nodes.services.identity_links import (
    Outcome,
    detect_after_key_write,
    detect_after_nodeinfo,
    evaluate_key,
    link_by_mac,
)
from nodes.signals import feeder_identity_changed, identity_link_live

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence

# PDYt, HELTEC_WIRELESS_PAPER (public values from the 2.8 hardware session).
PDYT_KEY_B64 = "I9+3Izg6g7w+TIU+EXGyFVYbh9m9sioXeo6RZdlwnS8="
PDYT_KEY = normalise_pubkey(PDYT_KEY_B64)
PDYT_OLD = 0x433B82F0  # 2.7 number: the last four bytes of the MAC
PDYT_NEW = 0x8959691B  # 2.8 number: crc32 of the key
PDYT_MAC_B64 = "SMpDO4Lw"
PDYT_MAC = "48:ca:43:3b:82:f0"

OTHER_KEY = "ab" * 32
THIRD_KEY = "cd" * 32


@pytest.fixture
def make_node(create_observed_node):
    """A Meshtastic row with identity fields derived from ``key`` (hex or base64) the way ingest does."""

    def make(number, key=None, **kwargs):
        if key is not None:
            kwargs.update(identity_fields(key))
            kwargs.setdefault("meshtastic_public_key", normalise_pubkey(key))
        kwargs.setdefault("mac_addr", None)
        return create_observed_node(meshtastic_node_id=number, **kwargs)

    return make


def links():
    return Link.objects.exclude(state=State.FLAGGED)


def flags():
    return Link.objects.filter(state=State.FLAGGED)


def test_pdyt_key_predicts_the_2_8_number_and_the_mac_the_2_7_number():
    assert key_node_id(PDYT_KEY_B64) == PDYT_NEW
    assert mac_node_number(PDYT_MAC) == PDYT_OLD
    assert mac_node_number(PDYT_MAC_B64) == PDYT_OLD
    assert mac_node_number("48ca433b82f0") == PDYT_OLD
    assert mac_node_number("00:00:00:00:00:00") is None
    assert mac_node_number("not a mac") is None


# --- key evidence ----------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_key_links_old_row_to_new_row_pdyt(make_node):
    old = make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    assert detect_after_key_write(new) == Outcome.CREATED
    link = links().get()
    assert (link.old_node, link.new_node) == (old, new)
    assert (link.evidence, link.confidence, link.state) == (Evidence.PUBLIC_KEY, "strong", State.AUTO)
    assert link.public_key_hex == PDYT_KEY
    assert not flags().exists()


@pytest.mark.django_db
def test_key_link_when_the_old_rows_key_arrives_after_the_new_row_exists(make_node):
    """The reverse arrival order gives the same single link."""
    make_node(PDYT_OLD)
    new = make_node(PDYT_NEW, PDYT_KEY)
    assert detect_after_key_write(new) == Outcome.NONE  # only one holder yet
    old = ObservedNode.objects.get(meshtastic_node_id=PDYT_OLD)
    for field, value in identity_fields(PDYT_KEY).items():
        setattr(old, field, value)
    old.save()
    detect_after_key_write(old)
    detect_after_key_write(new)  # and the other side asking again changes nothing
    link = links().get()
    assert (link.old_node.meshtastic_node_id, link.new_node.meshtastic_node_id) == (PDYT_OLD, PDYT_NEW)


@pytest.mark.django_db
def test_detection_is_idempotent(make_node):
    make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    assert detect_after_key_write(new) == Outcome.CREATED
    assert detect_after_key_write(new) == Outcome.UNCHANGED
    assert links().count() == 1


@pytest.mark.django_db
def test_native_2_8_node_gets_nothing(make_node):
    native = make_node(PDYT_NEW, PDYT_KEY)
    assert detect_after_key_write(native) == Outcome.NONE
    assert not Link.objects.exists()


@pytest.mark.django_db
def test_downgrade_changes_nothing(make_node):
    """A downgrade keeps the number and the key: the same row sends a new NodeInfo."""
    native = make_node(PDYT_NEW, PDYT_KEY)
    for _ in range(2):
        detect_after_nodeinfo(native, PDYT_MAC, key_written=True)
    assert not Link.objects.exists()


@pytest.mark.django_db
def test_shared_key_is_flagged_never_linked(make_node):
    new = make_node(PDYT_NEW, PDYT_KEY)
    make_node(PDYT_OLD, PDYT_KEY)
    make_node(0x11111111, PDYT_KEY)
    assert detect_after_key_write(new) == Outcome.FLAGGED_CREATED
    assert not links().exists()
    flag = flags().get()
    assert flag.old_node is None and flag.new_node is None
    assert flag.public_key_hex == PDYT_KEY
    assert [h["node_id"] for h in flag.detail["holders"]] == sorted([PDYT_NEW, PDYT_OLD, 0x11111111])
    assert detect_after_key_write(new) == Outcome.FLAGGED_UNCHANGED


@pytest.mark.django_db
def test_eighteen_holders_of_one_key_give_one_flagged_row(make_node):
    for number in range(0x20000000, 0x20000000 + 18):
        node = make_node(number, OTHER_KEY)
        detect_after_key_write(node)
    assert flags().count() == 1
    assert len(flags().get().detail["holders"]) == 18
    assert not links().exists()


@pytest.mark.django_db
def test_two_holders_neither_numbered_by_the_key_are_flagged(make_node):
    make_node(0x30000001, OTHER_KEY)
    other = make_node(0x30000002, OTHER_KEY)
    assert detect_after_key_write(other) == Outcome.FLAGGED_CREATED
    assert not links().exists()


@pytest.mark.django_db
def test_flag_is_removed_when_the_key_becomes_linkable(make_node):
    a = make_node(PDYT_OLD, PDYT_KEY)
    make_node(0x11111111, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    detect_after_key_write(new)
    assert flags().count() == 1
    ObservedNode.objects.filter(meshtastic_node_id=0x11111111).delete()
    assert detect_after_key_write(a) == Outcome.CREATED
    assert not flags().exists()


@pytest.mark.django_db
def test_meshcore_and_keyless_rows_are_ignored(make_node, create_observed_node):
    keyless = make_node(0x40000001)
    assert detect_after_key_write(keyless) == Outcome.NONE
    meshcore = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="e" * 64)
    assert detect_after_key_write(meshcore) == Outcome.NONE


# --- state rules ------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rejected_link_is_never_recreated_or_promoted(make_node):
    old = make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    Link.objects.create(old_node=old, new_node=new, evidence=Evidence.MAC, confidence="medium", state=State.REJECTED)
    assert detect_after_key_write(new) == Outcome.REJECTED
    assert links().get().state == State.REJECTED
    assert links().count() == 1


@pytest.mark.django_db
def test_suggested_link_is_promoted_by_key_evidence(make_node):
    old = make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    Link.objects.create(old_node=old, new_node=new, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)
    assert detect_after_key_write(new) == Outcome.PROMOTED
    link = links().get()
    assert (link.state, link.evidence, link.confidence) == (State.AUTO, Evidence.PUBLIC_KEY, "strong")
    assert link.detail["earlier"] == Evidence.MAC


@pytest.mark.django_db
def test_reverse_of_an_existing_pair_is_never_created(make_node):
    old = make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    Link.objects.create(old_node=new, new_node=old, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)
    assert detect_after_key_write(new) == Outcome.REVERSE
    assert links().count() == 1


@pytest.mark.django_db
def test_second_live_successor_is_refused_logged_and_ingest_continues(make_node, caplog):
    old = make_node(PDYT_OLD, PDYT_KEY)
    first_new = make_node(0x50000001)
    Link.objects.create(
        old_node=old, new_node=first_new, evidence=Evidence.FEEDER_REKEY, confidence="strong", state=State.AUTO
    )
    new = make_node(PDYT_NEW, PDYT_KEY)
    with caplog.at_level(logging.WARNING, logger=identity_links.logger.name):
        assert detect_after_key_write(new) == Outcome.CONFLICT
    assert "refused" in caplog.text
    assert links().count() == 1 and links().get().new_node == first_new


@pytest.mark.django_db
def test_database_refuses_two_live_predecessors_and_a_self_link(make_node):
    from django.db import IntegrityError, transaction

    a, b, c = make_node(0x60000001), make_node(0x60000002), make_node(0x60000003)
    Link.objects.create(old_node=a, new_node=c, evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.AUTO)
    with pytest.raises(IntegrityError), transaction.atomic():
        Link.objects.create(old_node=b, new_node=c, evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.AUTO)
    with pytest.raises(IntegrityError), transaction.atomic():
        Link.objects.create(old_node=a, new_node=a, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)
    # a non-live second predecessor is allowed
    Link.objects.create(old_node=b, new_node=c, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)


@pytest.mark.django_db
def test_detection_never_raises(make_node, caplog):
    new = make_node(PDYT_NEW, PDYT_KEY)
    with mock.patch.object(identity_links, "_key_holders", side_effect=RuntimeError("boom")):
        assert detect_after_key_write(new) == Outcome.NONE
    with mock.patch.object(identity_links, "link_by_mac", side_effect=RuntimeError("boom")):
        assert detect_after_nodeinfo(new, PDYT_MAC, key_written=False) == Outcome.NONE
    assert "failed" in caplog.text


@pytest.mark.django_db
def test_key_write_with_no_other_holder_costs_one_query(make_node):
    node = make_node(PDYT_NEW, PDYT_KEY)
    with CaptureQueriesContext(connection) as queries:
        detect_after_key_write(node)
    assert len(queries) == 1


@pytest.mark.django_db
def test_signal_is_sent_when_a_link_becomes_live(make_node, django_capture_on_commit_callbacks):
    seen = []

    def listener(sender, link, **kwargs):
        seen.append((link.pk, link.state))

    identity_link_live.connect(listener, weak=False)
    try:
        old = make_node(PDYT_OLD, PDYT_KEY)
        new = make_node(PDYT_NEW, PDYT_KEY)
        with django_capture_on_commit_callbacks(execute=True):
            detect_after_key_write(new)
        link = links().get()
        assert seen == [(link.pk, State.AUTO)]

        # a suggestion is not live; promoting it is
        other_old = make_node(0x70000001)
        other_new = make_node(0x70000002)
        with django_capture_on_commit_callbacks(execute=True):
            identity_links.record_link(
                other_old, other_new, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
            )
        assert len(seen) == 1
        with django_capture_on_commit_callbacks(execute=True):
            identity_links.record_link(
                other_old, other_new, evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.AUTO
            )
        assert len(seen) == 2 and seen[1][1] == State.AUTO
        assert old and new
    finally:
        identity_link_live.disconnect(listener)


@pytest.mark.django_db
def test_failing_signal_receiver_does_not_break_detection(make_node, django_capture_on_commit_callbacks, caplog):
    def listener(sender, link, **kwargs):
        raise RuntimeError("receiver bug")

    identity_link_live.connect(listener, weak=False)
    try:
        make_node(PDYT_OLD, PDYT_KEY)
        new = make_node(PDYT_NEW, PDYT_KEY)
        with django_capture_on_commit_callbacks(execute=True):
            detect_after_key_write(new)
        assert "receiver" in caplog.text
        assert links().count() == 1
    finally:
        identity_link_live.disconnect(listener)


# --- MAC evidence -----------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_mac_only_suggests_the_same_pair_pdyt(make_node):
    old = make_node(PDYT_OLD)
    new = make_node(PDYT_NEW)
    assert link_by_mac(new, PDYT_MAC) == Outcome.CREATED
    link = links().get()
    assert (link.old_node, link.new_node) == (old, new)
    assert (link.evidence, link.confidence, link.state) == (Evidence.MAC, "medium", State.SUGGESTED)
    assert link_by_mac(new, PDYT_MAC) == Outcome.NONE  # already in a link: no more MAC work


@pytest.mark.django_db
def test_mac_accepts_the_wire_base64_form(make_node):
    make_node(PDYT_OLD)
    new = make_node(PDYT_NEW)
    assert link_by_mac(new, PDYT_MAC_B64) == Outcome.CREATED


@pytest.mark.django_db
def test_mac_two_candidates_record_nothing(make_node):
    make_node(PDYT_OLD)
    make_node(0x80000001, mac_addr=PDYT_MAC)
    new = make_node(PDYT_NEW)
    assert link_by_mac(new, PDYT_MAC) == Outcome.NONE
    assert not Link.objects.exists()


@pytest.mark.django_db
def test_mac_same_stored_mac_links_the_key_numbered_row_as_new(make_node):
    """A full erase mints a new key: only the MAC can suggest the link."""
    old = make_node(0x90000001, OTHER_KEY, mac_addr=PDYT_MAC)
    new = make_node(PDYT_NEW, PDYT_KEY)
    assert link_by_mac(new, PDYT_MAC) == Outcome.CREATED
    link = links().get()
    assert (link.old_node, link.new_node, link.state) == (old, new, State.SUGGESTED)


@pytest.mark.django_db
def test_mac_candidate_with_the_same_key_is_key_territory_not_mac(make_node):
    make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    assert link_by_mac(new, PDYT_MAC) == Outcome.NONE


@pytest.mark.django_db
def test_mac_blank_or_zero_never_links(make_node):
    make_node(0xC0000001, mac_addr="00:00:00:00:00:00")
    new = make_node(PDYT_NEW)
    assert link_by_mac(new, "00:00:00:00:00:00") == Outcome.NONE
    assert link_by_mac(new, None) == Outcome.NONE


@pytest.mark.django_db
def test_mac_rows_numbered_by_their_own_mac_find_no_candidate(make_node):
    """A 2.7 node's MAC tail is its own number: no other row, no link."""
    node = make_node(PDYT_OLD)
    assert link_by_mac(node, PDYT_MAC) == Outcome.NONE


# --- managed feeder re-key --------------------------------------------------------------------------------------


@pytest.fixture
def feeder_event(create_managed_node, create_user):
    def make(outcome, old=PDYT_OLD, new=PDYT_NEW, **extra):
        feeder = create_managed_node(meshtastic_node_id=old, name="Feeder")
        return feeder, ManagedNodeIdentityEvent.objects.create(
            managed_node=feeder,
            old_meshtastic_node_id=old,
            new_meshtastic_node_id=new,
            outcome=outcome,
            **extra,
        )

    return make


def _send(feeder, event, send=True):
    fire = feeder_identity_changed.send if send else feeder_identity_changed.send_robust
    return fire(
        sender=type(feeder),
        managed_node=feeder,
        event=event,
        old_node_id=event.old_meshtastic_node_id,
        new_node_id=event.new_meshtastic_node_id,
    )


@pytest.mark.django_db
def test_feeder_auto_rekey_creates_an_auto_link(make_node, feeder_event):
    old, new = make_node(PDYT_OLD), make_node(PDYT_NEW)
    feeder, event = feeder_event(ManagedNodeIdentityEvent.Outcome.AUTO_UPDATED)
    with mock.patch("nodes.services.feeder_identity_notify.queue_owner_notification"):
        _send(feeder, event)
    link = links().get()
    assert (link.old_node, link.new_node) == (old, new)
    assert (link.evidence, link.state, link.confidence) == (Evidence.FEEDER_REKEY, State.AUTO, "strong")


@pytest.mark.django_db
def test_feeder_manual_repoint_is_confirmed_and_merges_with_the_key_link(make_node, feeder_event, create_user):
    make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    detect_after_key_write(new)
    reviewer = create_user()
    feeder, event = feeder_event(ManagedNodeIdentityEvent.Outcome.MANUAL, acknowledged_by=reviewer)
    _send(feeder, event)
    link = links().get()
    assert (link.state, link.evidence) == (State.CONFIRMED, Evidence.PUBLIC_KEY)
    assert link.detail["also"] == [Evidence.FEEDER_REKEY]
    assert link.reviewed_by == reviewer


@pytest.mark.django_db
def test_feeder_rekey_without_both_rows_links_nothing(make_node, feeder_event):
    make_node(PDYT_OLD)
    feeder, event = feeder_event(ManagedNodeIdentityEvent.Outcome.MANUAL)
    _send(feeder, event)
    assert not Link.objects.exists()


@pytest.mark.django_db
def test_feeder_receiver_never_raises_even_with_plain_send(make_node, feeder_event, caplog):
    """repoint_feeder uses plain send: an exception here would turn a committed re-point into a 500."""
    make_node(PDYT_OLD)
    make_node(PDYT_NEW)
    feeder, event = feeder_event(ManagedNodeIdentityEvent.Outcome.MANUAL)
    with mock.patch.object(identity_links, "link_feeder_rekey", side_effect=RuntimeError("boom")):
        _send(feeder, event, send=True)
    with mock.patch("nodes.services.identity_links.detect_after_feeder_rekey", side_effect=RuntimeError("boom")):
        _send(feeder, event, send=True)
    assert "failed" in caplog.text
    assert not Link.objects.exists()


# --- the command ------------------------------------------------------------------------------------------------


def _seed_command_data(make_node):
    make_node(PDYT_OLD, PDYT_KEY)
    make_node(PDYT_NEW, PDYT_KEY)  # linkable pair
    for number in range(0xA0000000, 0xA0000000 + 5):
        make_node(number, OTHER_KEY)  # a cloned key
    make_node(0xB0000001, THIRD_KEY)  # unshared


def _run(*args):
    out = StringIO()
    call_command("detect_meshtastic_identity_links", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_command_dry_run_reports_the_same_numbers_as_a_real_run_and_writes_nothing(make_node):
    _seed_command_data(make_node)
    dry = _run("--dry-run", "--batch-size", "1")
    assert not Link.objects.exists()
    real = _run("--batch-size", "1")
    assert dry.replace("[dry-run] ", "") == real
    assert links().count() == 1 and links().get().state == State.AUTO
    assert flags().count() == 1
    assert "Unlinkable (shared) keys: 1" in real
    assert "Links created 1" in real and "Flagged rows created 1" in real
    assert "auto 1" in real and "flagged 1" in real


@pytest.mark.django_db
def test_command_second_real_run_changes_nothing(make_node):
    _seed_command_data(make_node)
    _run()
    before = list(Link.objects.order_by("pk").values_list("pk", "state", "updated_at"))
    second = _run()
    assert list(Link.objects.order_by("pk").values_list("pk", "state", "updated_at")) == before
    assert (
        "Links created 0" in second and "Flagged rows created 0" in second and "Unlinkable (shared) keys: 1" in second
    )


@pytest.mark.django_db
def test_command_with_nothing_to_do(make_node):
    make_node(PDYT_NEW, PDYT_KEY)
    out = _run()
    assert "1 keyed Meshtastic rows; 0 key(s) held by more than one row" in out
    assert evaluate_key(PDYT_KEY) == Outcome.NONE


# --- admin ------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_lists_filters_searches_and_staff_can_change_state(make_node, admin_client, admin_user):
    old = make_node(PDYT_OLD, PDYT_KEY)
    new = make_node(PDYT_NEW, PDYT_KEY)
    detect_after_key_write(new)
    link = links().get()
    assert Link in django_admin.site._registry

    base = "/admin/nodes/observednodeidentitylink/"
    listing = admin_client.get(base, {"state": "auto", "evidence": "public_key", "q": "!8959691b"})
    assert listing.status_code == 200
    assert listing.context["cl"].result_count == 1
    assert admin_client.get(base, {"q": "433b82f0"}).context["cl"].result_count == 1
    assert admin_client.get(base, {"q": "!11111111"}).context["cl"].result_count == 0

    response = admin_client.post(f"{base}{link.pk}/change/", {"state": "rejected"})
    assert response.status_code == 302
    link.refresh_from_db()
    assert link.state == State.REJECTED and link.reviewed_by == admin_user and link.reviewed_at
    assert old and new


@pytest.mark.django_db
def test_admin_confirming_a_link_sends_the_live_signal(make_node, admin_client, django_capture_on_commit_callbacks):
    old = make_node(0x70000001)
    new = make_node(0x70000002)
    link = identity_links.record_link(old, new, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)
    assert link == Outcome.CREATED
    row = links().get()
    seen = []

    def listener(sender, link, **kwargs):
        seen.append((link.pk, link.state))

    identity_link_live.connect(listener, weak=False)
    try:
        base = "/admin/nodes/observednodeidentitylink/"
        with django_capture_on_commit_callbacks(execute=True):
            assert admin_client.post(f"{base}{row.pk}/change/", {"state": "confirmed"}).status_code == 302
        assert seen == [(row.pk, State.CONFIRMED)]
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"{base}{row.pk}/change/", {"state": "rejected"})
        assert len(seen) == 1  # leaving the live set sends nothing
    finally:
        identity_link_live.disconnect(listener)


@pytest.mark.django_db
def test_admin_rejecting_a_suggestion_sends_nothing(make_node, admin_client, django_capture_on_commit_callbacks):
    old = make_node(0x70000001)
    new = make_node(0x70000002)
    identity_links.record_link(old, new, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED)
    row = links().get()
    seen = []
    listener = lambda sender, link, **kw: seen.append(link.pk)  # noqa: E731
    identity_link_live.connect(listener, weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/admin/nodes/observednodeidentitylink/{row.pk}/change/", {"state": "rejected"})
        assert seen == []
    finally:
        identity_link_live.disconnect(listener)


# --- a key that becomes shared after it was linked ---------------------------------------------------------------


@pytest.mark.django_db
def test_auto_key_link_is_retired_when_the_key_gains_a_third_holder(make_node):
    new = make_node(PDYT_NEW, PDYT_KEY)
    make_node(PDYT_OLD, PDYT_KEY)
    detect_after_key_write(new)
    assert links().get().state == State.AUTO

    third = make_node(0x11111111, PDYT_KEY)
    assert detect_after_key_write(third) == Outcome.FLAGGED_CREATED

    link = links().get()
    assert link.state == State.SUGGESTED and link.detail["key_now_shared"] is True
    assert not Link.objects.filter(state__in=Link.LIVE_STATES).exists()
    assert flags().count() == 1


@pytest.mark.django_db
def test_confirmed_key_link_survives_the_key_becoming_shared(make_node):
    new = make_node(PDYT_NEW, PDYT_KEY)
    make_node(PDYT_OLD, PDYT_KEY)
    detect_after_key_write(new)
    Link.objects.update(state=State.CONFIRMED)

    third = make_node(0x11111111, PDYT_KEY)
    detect_after_key_write(third)

    assert links().get().state == State.CONFIRMED
    assert flags().count() == 1


@pytest.mark.django_db
def test_feeder_rekey_link_survives_the_key_becoming_shared(make_node):
    new = make_node(PDYT_NEW, PDYT_KEY)
    make_node(PDYT_OLD, PDYT_KEY)
    identity_links.link_feeder_rekey(PDYT_OLD, PDYT_NEW, manual=False)
    third = make_node(0x11111111, PDYT_KEY)
    detect_after_key_write(third)
    assert links().get().state == State.AUTO and links().get().evidence == Evidence.FEEDER_REKEY
    assert new
