import pytest

from traceroute.models import AutoTraceRoute
from traceroute.target_strategy_query import target_strategy_tokens_to_q


def test_target_strategy_tokens_to_q_returns_none_for_invalid_only():
    assert target_strategy_tokens_to_q(["not_a_real_strategy"]) is None


def test_target_strategy_tokens_to_q_accepts_strategy_key():
    q = target_strategy_tokens_to_q([AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE])
    assert q is not None


@pytest.mark.django_db
def test_legacy_token_matches_rows_with_null_target_strategy(
    create_managed_node,
    create_observed_node,
    create_user,
):
    """Regression: legacy filter matches null strategy (matches list + reach semantics)."""
    from traceroute.tests.factories import make_auto_traceroute

    user = create_user()
    mn = create_managed_node()
    on = create_observed_node()
    legacy_row = make_auto_traceroute(
        create_managed_node,
        create_observed_node,
        create_user,
        source_node=mn,
        target_node=on,
        triggered_by=user,
        target_strategy=None,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )
    make_auto_traceroute(
        create_managed_node,
        create_observed_node,
        create_user,
        source_node=mn,
        target_node=on,
        triggered_by=user,
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )
    fq = target_strategy_tokens_to_q(["legacy"])
    assert fq is not None
    qs = AutoTraceRoute.objects.filter(fq)
    assert qs.filter(pk=legacy_row.pk).exists()
    assert qs.count() == 1
