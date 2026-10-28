"""Independent literal expectations for all fictional policy boundaries."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from policydesk.models import TODAY, Extraction, Order, money
from policydesk.policy import evaluate


def order(**updates) -> Order:
    values = {
        "order_id": "GN-TEST",
        "customer_id": "C-01",
        "currency": "BRL",
        "items": [{"name": "Fictional coffee", "price": "79.90"}],
        "shipping_fee": "14.90",
        "status": "delivered",
        "shipped_at": "2026-09-01",
        "estimated_delivery": "2026-10-01",
        "delivered_at": "2026-10-26",
        "carrier_status": "delivered",
        "subscription_id": None,
    }
    return Order.model_validate({**values, **updates})


def extraction(**updates) -> Extraction:
    return Extraction.model_validate(
        {
            "language": "en",
            "intent": "refund_request",
            "order_id": "GN-TEST",
            "claim": "changed_mind",
            "customer_stated_amount": None,
            **updates,
        }
    )


@pytest.mark.parametrize(
    "claim,delivered,outcome,amount,clause",
    [
        ("changed_mind", "2026-10-26", "approve", "79.90", "RF-1"),
        ("changed_mind", "2026-10-25", "deny", None, "RF-1"),
        ("damaged", "2026-10-03", "approve", "94.80", "RF-2"),
        ("damaged", "2026-10-02", "deny", None, "RF-2"),
        ("wrong_item", "2026-10-03", "approve", "94.80", "RF-2"),
        ("wrong_item", "2026-10-02", "deny", None, "RF-2"),
    ],
)
def test_return_windows(claim, delivered, outcome, amount, clause):
    decision = evaluate(extraction(claim=claim), order(delivered_at=delivered), "C-01", TODAY)
    assert decision.outcome == outcome
    assert decision.clause_ids == [clause]
    assert (str(decision.refund.amount) if decision.refund else None) == amount


@pytest.mark.parametrize(
    "estimate,carrier,outcome",
    [
        ("2026-10-24", "in_transit", "deny"),
        ("2026-10-23", "in_transit", "approve"),
        ("2026-10-23", "delivered", "needs_human"),
        ("2026-11-05", "in_transit", "deny"),
    ],
)
def test_delivery_lateness(estimate, carrier, outcome):
    decision = evaluate(
        extraction(claim="not_delivered"),
        order(
            status="in_transit",
            delivered_at=None,
            estimated_delivery=estimate,
            carrier_status=carrier,
        ),
        "C-01",
        TODAY,
    )
    assert decision.outcome == outcome
    assert decision.clause_ids == ["RF-3"]


@pytest.mark.parametrize(
    "currency,limit", [("BRL", "400.00"), ("MXN", "1500.00"), ("USD", "80.00")]
)
@pytest.mark.parametrize(
    "delta,outcome", [("-0.01", "approve"), ("0", "approve"), ("0.01", "needs_human")]
)
def test_refund_limits(currency, limit, delta, outcome):
    decision = evaluate(
        extraction(claim="damaged"),
        order(
            currency=currency,
            items=[{"name": "Fictional coffee", "price": str(Decimal(limit) + Decimal(delta))}],
            shipping_fee="0.00",
        ),
        "C-01",
        TODAY,
    )
    assert decision.outcome == outcome
    assert decision.clause_ids == (["RF-2", "LM-1"] if outcome == "needs_human" else ["RF-2"])
    assert bool(decision.actions) == (outcome == "approve")


@pytest.mark.parametrize("shipped", [True, False])
def test_subscription_separate_actions(shipped):
    candidate = (
        order(subscription_id="SUB-01")
        if shipped
        else order(
            subscription_id="SUB-01",
            status="processing",
            shipped_at=None,
            delivered_at=None,
            carrier_status="in_transit",
        )
    )
    decision = evaluate(
        extraction(intent="cancel_subscription", claim="none"), candidate, "C-01", TODAY
    )
    assert [a.kind for a in decision.actions] == (
        ["cancel_subscription"] if shipped else ["cancel_subscription", "refund"]
    )
    assert decision.actions[0].amount is None
    assert decision.actions[0].subscription_id == "SUB-01"


def test_over_limit_subscription_escalates_entire_request():
    candidate = order(
        subscription_id="SUB-01",
        status="processing",
        shipped_at=None,
        delivered_at=None,
        carrier_status="in_transit",
        items=[{"name": "Fictional coffee", "price": "500.00"}],
    )
    decision = evaluate(
        extraction(intent="cancel_subscription", claim="none"), candidate, "C-01", TODAY
    )
    assert decision.outcome == "needs_human"
    assert decision.actions == []
    assert decision.clause_ids == ["SB-1", "LM-1"]


def test_ownership_precedes_policy_and_amount():
    decision = evaluate(extraction(), order(), "C-OTHER", TODAY)
    assert decision.outcome == "needs_human"
    assert decision.clause_ids == ["ID-1"]
    assert decision.actions == []


def test_customer_amount_is_ignored():
    decision = evaluate(extraction(customer_stated_amount="999999.00"), order(), "C-01", TODAY)
    assert decision.refund is not None
    assert decision.refund.amount == Decimal("79.90")


def test_shipping_information_is_explicit():
    decision = evaluate(extraction(intent="shipping_status", claim="none"), order(), "C-01", TODAY)
    assert decision.outcome == "information"
    assert decision.actions == []
    assert decision.reasons == ["carrier_delivered"]


@pytest.mark.parametrize(
    "language,status_word", [("pt", "entregue"), ("es", "entregado"), ("en", "delivered")]
)
def test_shipping_reply_includes_the_actual_carrier_status(language, status_word):
    from policydesk.replies import render

    decision = evaluate(extraction(intent="shipping_status", claim="none"), order(), "C-01", TODAY)
    assert status_word in render(decision, language).body


@pytest.mark.parametrize(
    "updates",
    [
        {"intent": "other", "claim": "none"},
        {"intent": "cancel_subscription", "claim": "none"},
        {"claim": "none"},
        {"order_id": "UNKNOWN"},
    ],
)
def test_unsupported_or_unresolved_hands_off(updates):
    assert evaluate(extraction(**updates), order(), "C-01", TODAY).outcome == "needs_human"


@pytest.mark.parametrize(
    "value",
    ["-0.01", "NaN", "Infinity", "1000000001", 1.1, True, "abc", "1e2", "+1", " 1.20 ", "-0.00"],
)
def test_invalid_money_is_rejected(value):
    with pytest.raises(ValueError):
        money(value)


def test_rounding_is_half_up():
    assert money("1.005") == Decimal("1.01")
    assert money("1.004") == Decimal("1.00")


def test_json_money_requires_a_string_not_an_integer():
    from policydesk.models import Item

    with pytest.raises(ValidationError):
        Item.model_validate_json('{"name":"Fictional coffee","price":10}')
    assert Item.model_validate_json('{"name":"Fictional coffee","price":"10"}').price == Decimal(
        "10.00"
    )


@pytest.mark.parametrize("value", ["2026-11-02T00:00:00Z", "2026-11-02T00:00:00", 0, "20261102"])
def test_order_dates_require_exact_calendar_representations(value):
    with pytest.raises(ValidationError):
        order(estimated_delivery=value)


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "processing"},
        {"delivered_at": None},
        {"shipped_at": None},
        {"delivered_at": "2026-08-31"},
        {"estimated_delivery": "2026-08-31"},
        {"currency": "EUR"},
    ],
)
def test_inconsistent_order_is_rejected(updates):
    with pytest.raises(ValidationError):
        order(**updates)


def test_future_delivery_is_rejected_by_evaluation_date():
    with pytest.raises(ValueError, match="future"):
        evaluate(extraction(), order(delivered_at="2026-11-03"), "C-01", TODAY)
    assert (
        evaluate(extraction(), order(delivered_at="2026-11-03"), "C-01", date(2026, 11, 4)).outcome
        == "approve"
    )
