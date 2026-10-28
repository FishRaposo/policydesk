"""Every adversarial fixture names the guard it must trip."""

from decimal import Decimal

import pytest

from policydesk.models import Decision, DraftReply
from policydesk.replies import render
from policydesk.validators import body_money, check


def decision(outcome="approve", amount="94.80", currency="BRL", clauses=None):
    return Decision.model_validate(
        {
            "outcome": outcome,
            "actions": [
                {
                    "kind": "refund",
                    "order_id": "GN-TEST",
                    "amount": amount,
                    "currency": currency,
                    "subscription_id": None,
                }
            ]
            if outcome == "approve"
            else [],
            "clause_ids": clauses if clauses is not None else ["RF-2"],
            "reasons": ["test"],
        }
    )


@pytest.mark.parametrize("lang", ["pt", "es", "en"])
@pytest.mark.parametrize("outcome", ["approve", "deny", "needs_human", "information"])
def test_clean_templates_pass_all_eight_checks(lang, outcome):
    d = decision(outcome=outcome)
    assert check(render(d, lang), d, lang) == []


BAD_DRAFTS = [
    ("approve", {"stated_amount": "94.81"}, "amount_matches"),
    ("approve", {"stated_currency": "USD"}, "amount_matches"),
    (
        "approve",
        {"body": "Your request is pending human confirmation. R$ 94,81."},
        "body_money_matches",
    ),
    (
        "approve",
        {"body": "Your request is pending human confirmation. R$94.81."},
        "body_money_matches",
    ),
    (
        "approve",
        {"body": "Your request is pending human confirmation. USD 94.80."},
        "body_money_matches",
    ),
    (
        "approve",
        {"body": "Your request is pending human confirmation. MX$94.80."},
        "body_money_matches",
    ),
    (
        "approve",
        {"body": "Your request is pending human confirmation. 94.80."},
        "body_money_matches",
    ),
    ("approve", {"body": "Your request is pending human confirmation."}, "body_money_matches"),
    (
        "approve",
        {"body": "Your request is pending human confirmation. $94.80."},
        "body_money_matches",
    ),
    (
        "approve",
        {"body": "Your request is pending human confirmation. R$94.80 USD."},
        "body_money_matches",
    ),
    ("approve", {"cited_clause_ids": ["RF-1"]}, "clauses_subset"),
    ("approve", {"cited_clause_ids": []}, "clauses_subset"),
    ("approve", {"cited_clause_ids": ["RF-2", "RF-2"]}, "clauses_subset"),
    ("approve", {"next_step": "denied"}, "next_step_consistent"),
    (
        "deny",
        {"body": "Your refund approved request will be processed soon."},
        "no_unapproved_promise",
    ),
    ("deny", {"body": "We will refund the order after a support review."}, "no_unapproved_promise"),
    (
        "deny",
        {"body": "We'll refund this order as requested by the customer."},
        "no_unapproved_promise",
    ),
    (
        "deny",
        {"body": "O reembolso aprovado será enviado para você em breve."},
        "no_unapproved_promise",
    ),
    (
        "deny",
        {"body": "Vamos reembolsar o valor integral do pedido para você."},
        "no_unapproved_promise",
    ),
    (
        "deny",
        {"body": "El reembolso aprobado será enviado al cliente pronto."},
        "no_unapproved_promise",
    ),
    ("deny", {"body": "Te devolvemos todo el dinero del pedido ahora."}, "no_unapproved_promise"),
    ("approve", {"body": "Your order has been refunded. BRL 94.80."}, "no_completed_claim"),
    ("approve", {"body": "Your refund is complete. BRL 94.80."}, "no_completed_claim"),
    ("approve", {"body": "Your order was already refunded. BRL 94.80."}, "no_completed_claim"),
    ("approve", {"body": "O pedido já foi reembolsado. BRL 94.80."}, "no_completed_claim"),
    ("approve", {"body": "El pedido ya fue reembolsado. BRL 94.80."}, "no_completed_claim"),
    ("deny", {"next_step": "refund_pending_confirmation"}, "next_step_consistent"),
    ("deny", {"stated_amount": "94.80", "stated_currency": "BRL"}, "amount_matches"),
    (
        "deny",
        {
            "body": "Sua solicitação precisa ser analisada por uma pessoa da equipe de suporte antes de autorizar qualquer ação."
        },
        "language_matches",
    ),
    (
        "deny",
        {
            "body": "Su solicitud necesita una revisión por parte de una persona de soporte antes de autorizar cualquier acción."
        },
        "language_matches",
    ),
]


@pytest.mark.parametrize("outcome,updates,expected", BAD_DRAFTS)
def test_adversarial_draft_is_blocked(outcome, updates, expected):
    d = decision(outcome=outcome)
    draft = DraftReply.model_validate({**render(d, "en").model_dump(mode="json"), **updates})
    assert expected in [v.code for v in check(draft, d, "en")]


@pytest.mark.parametrize("secret", ["GN-1009", "PRIVATE-SENTINEL-ITEM", "PRIVATE-SENTINEL-ADDRESS"])
def test_privileged_foreign_sentinels_never_pass(secret):
    d = decision(outcome="needs_human", clauses=["ID-1"])
    draft = render(d, "en").model_copy(update={"body": render(d, "en").body + " " + secret})
    assert "no_foreign_order_data" in [v.code for v in check(draft, d, "en", (secret,))]


@pytest.mark.parametrize(
    "body,context,amount,currency",
    [
        ("R$ 89,90", "BRL", "89.90", "BRL"),
        ("R$89.90", "BRL", "89.90", "BRL"),
        ("$1,234.00 MXN", "MXN", "1234.00", "MXN"),
        ("MX$1,234", "MXN", "1234", "MXN"),
        ("US$ 45.00", "USD", "45", "USD"),
        ("$45", "USD", "45", "USD"),
        ("94,80 BRL", "BRL", "94.80", "BRL"),
        ("BRL 1.234,56", "BRL", "1234.56", "BRL"),
    ],
)
def test_money_formats(body, context, amount, currency):
    assert body_money(body, context) == [(Decimal(amount), currency)]
