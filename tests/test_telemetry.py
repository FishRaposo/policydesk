"""Spend ceilings are enforced using Decimal and conservative reservations."""

import importlib.util
from decimal import Decimal

import pytest


def test_unknown_reservation_remains_after_acknowledgement():
    assert importlib.util.find_spec("policydesk.telemetry") is not None, (
        "Session accounting is absent"
    )
    from policydesk.telemetry import BudgetExceeded, SessionBudget

    session = SessionBudget(Decimal("1"))
    reservation = session.reserve(Decimal("0.60"))
    session.mark_unknown(reservation)
    with pytest.raises(BudgetExceeded):
        session.reserve(Decimal("0.01"))
    session.acknowledge_unknown()
    assert session.summary()["reserved_usd"] == "0.60"
    with pytest.raises(BudgetExceeded):
        session.reserve(Decimal("0.41"))
    session.reserve(Decimal("0.40"))


def test_cache_write_and_reasoning_usage_are_priced_once():
    from policydesk.telemetry import profile_for, usage_cost, worst_cost

    profile = profile_for("gpt-6-luna")
    usage = {
        "input_tokens": 1000,
        "output_tokens": 100,
        "input_tokens_details": {"cached_tokens": 400, "cache_write_tokens": 200},
        "output_tokens_details": {"reasoning_tokens": 80},
    }
    assert usage_cost(profile, usage) == Decimal("0.000119")
    assert worst_cost(profile, 1000, 100) == Decimal("0.000175")


@pytest.mark.parametrize(
    "value", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.0]
)
def test_invalid_session_limits_are_rejected(value):
    from policydesk.telemetry import SessionBudget

    with pytest.raises(ValueError):
        SessionBudget(value)


def test_missing_cache_write_usage_is_unknown_instead_of_underpriced():
    from policydesk.telemetry import profile_for, usage_cost

    with pytest.raises(KeyError):
        usage_cost(
            profile_for("gpt-6-luna"),
            {
                "input_tokens": 100,
                "output_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        )
