"""Deterministic fictional policy. Customer claims never supply the amount."""

from datetime import date
from decimal import Decimal

from .models import Decision, Extraction, Order, ProposedAction
from .resources import load_policy


def evaluate(
    extraction: Extraction,
    order: Order | None,
    customer_id: str,
    today: date,
    *,
    ownership_denied: bool = False,
) -> Decision:
    policy = load_policy()

    def result(
        outcome: str, clauses: list[str], reason: str, actions: list[ProposedAction] | None = None
    ) -> Decision:
        return Decision.model_validate(
            {
                "outcome": outcome,
                "clause_ids": clauses,
                "reasons": [reason],
                "actions": actions or [],
            }
        )

    if ownership_denied or (order and order.customer_id != customer_id):
        return result("needs_human", ["ID-1"], "ownership_denied")
    if order is None:
        return result("needs_human", ["XX-0"], "order_unresolved")
    order.validate_date(today)
    if extraction.order_id != order.order_id:
        return result("needs_human", ["XX-0"], "order_unresolved")
    if extraction.intent == "shipping_status" and extraction.claim == "none":
        return result("information", [], f"carrier_{order.carrier_status}")

    actions: list[ProposedAction] = []
    amount: Decimal | None = None
    clause: str
    if extraction.intent == "cancel_subscription":
        if not order.subscription_id:
            return result("needs_human", ["XX-0"], "subscription_unresolved")
        clause = "SB-1"
        actions.append(
            ProposedAction(
                kind="cancel_subscription",
                order_id=order.order_id,
                amount=None,
                currency=None,
                subscription_id=order.subscription_id,
            )
        )
        if order.shipped_at is None:
            amount = order.subtotal + order.shipping_fee
    elif extraction.intent == "refund_request":
        if extraction.claim in ("changed_mind", "damaged", "wrong_item"):
            clause = "RF-1" if extraction.claim == "changed_mind" else "RF-2"
            if order.delivered_at is None:
                return result("needs_human", [clause], "delivery_unconfirmed")
            if (today - order.delivered_at).days > int(policy["windows"][clause]):
                return result("deny", [clause], "outside_window")
            amount = order.subtotal if clause == "RF-1" else order.subtotal + order.shipping_fee
        elif extraction.claim == "not_delivered":
            clause = "RF-3"
            if order.carrier_status == "delivered" or order.delivered_at is not None:
                return result("needs_human", [clause], "carrier_dispute")
            if (today - order.estimated_delivery).days < int(policy["windows"][clause]):
                return result("deny", [clause], "not_late_enough")
            amount = order.subtotal + order.shipping_fee
        else:
            return result("needs_human", ["XX-0"], "unsupported_claim")
    else:
        return result("needs_human", ["XX-0"], "unsupported_intent")

    if amount is not None:
        if amount > Decimal(policy["limits"][order.currency]):
            return result("needs_human", [clause, "LM-1"], "refund_over_limit")
        actions.append(
            ProposedAction(
                kind="refund",
                order_id=order.order_id,
                amount=amount,
                currency=order.currency,
                subscription_id=None,
            )
        )
    return result("approve", [clause], "pending_confirmation", actions)
