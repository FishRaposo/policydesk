"""Validated application contracts. Money crosses JSON boundaries as strings."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Language = Literal["pt", "es", "en"]
Currency = Literal["BRL", "MXN", "USD"]
Intent = Literal["refund_request", "cancel_subscription", "shipping_status", "other"]
Claim = Literal["changed_mind", "damaged", "wrong_item", "not_delivered", "none"]
Outcome = Literal["approve", "deny", "needs_human", "information"]
TODAY = date(2026, 11, 2)


def money(value: object) -> Decimal:
    if isinstance(value, (float, bool)) or not isinstance(value, (str, Decimal, int)):
        raise ValueError("Money must be a decimal string")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > Decimal("1000000000"):
            raise ValueError("Money must be finite, nonnegative and at most 1000000000")
        return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal money") from exc


Money = Annotated[Decimal, BeforeValidator(money)]
Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Item(Contract):
    name: str = Field(min_length=1, max_length=120)
    price: Money


class Order(Contract):
    order_id: Identifier
    customer_id: Identifier
    currency: Currency
    items: list[Item] = Field(min_length=1, max_length=20)
    shipping_fee: Money
    status: Literal["delivered", "in_transit", "processing"]
    shipped_at: date | None
    estimated_delivery: date
    delivered_at: date | None
    carrier_status: Literal["delivered", "in_transit", "exception"]
    subscription_id: Identifier | None

    @model_validator(mode="after")
    def coherent(self) -> "Order":
        if self.status == "processing" and (self.shipped_at or self.delivered_at):
            raise ValueError("Processing orders cannot have shipment or delivery dates")
        if self.status != "processing" and self.shipped_at is None:
            raise ValueError("Shipped orders need shipped_at")
        if (self.status == "delivered") != (self.delivered_at is not None):
            raise ValueError("Delivery date must match delivered status")
        if self.shipped_at and self.delivered_at and self.delivered_at < self.shipped_at:
            raise ValueError("Delivery cannot precede shipment")
        if self.shipped_at and self.estimated_delivery < self.shipped_at:
            raise ValueError("Estimate cannot precede shipment")
        if sum((item.price for item in self.items), Decimal(0)) + self.shipping_fee > Decimal(
            "1000000000"
        ):
            raise ValueError("Order total exceeds supported money range")
        return self

    @property
    def subtotal(self) -> Decimal:
        return sum((item.price for item in self.items), Decimal("0.00"))

    def validate_date(self, today: date) -> None:
        if any(d and d > today for d in (self.shipped_at, self.delivered_at)):
            raise ValueError("Shipment and delivery cannot be in the future")


class Ticket(Contract):
    customer_id: Identifier
    language: Language
    message: str = Field(min_length=1, max_length=8000)


class Extraction(Contract):
    language: Language
    intent: Intent
    order_id: Identifier | None
    claim: Claim
    customer_stated_amount: Money | None


class ProposedAction(Contract):
    kind: Literal["refund", "cancel_subscription"]
    order_id: Identifier
    amount: Money | None
    currency: Currency | None
    subscription_id: Identifier | None

    @model_validator(mode="after")
    def valid_action(self) -> "ProposedAction":
        if self.kind == "refund" and (self.amount is None or self.currency is None):
            raise ValueError("Refund requires amount and currency")
        if self.kind == "cancel_subscription" and (
            not self.subscription_id or self.amount is not None or self.currency is not None
        ):
            raise ValueError("Cancellation requires a subscription and no money")
        return self


class Decision(Contract):
    outcome: Outcome
    actions: list[ProposedAction]
    clause_ids: list[str]
    policy_version: str = "v1"
    reasons: list[str]

    @property
    def refund(self) -> ProposedAction | None:
        return next((a for a in self.actions if a.kind == "refund"), None)


class DraftReply(Contract):
    body: str = Field(min_length=1, max_length=6000)
    cited_clause_ids: list[str]
    stated_amount: Money | None
    stated_currency: Currency | None
    next_step: Literal[
        "refund_pending_confirmation",
        "cancellation_pending_confirmation",
        "denied",
        "handed_off",
        "information",
    ]


class Violation(Contract):
    code: str
    detail: str
