"""Conservative per-session reservations and provider-reported token accounting."""

import json
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import uuid4

from .resources import DATA

LIVE_LIMITS = {
    "max_tool_calls": 3,
    "max_generation_requests": 6,
    "max_output_tokens": 2048,
    "max_input_tokens": 32000,
    "request_timeout_seconds": 30,
    "pipeline_deadline_seconds": 120,
}


class BudgetExceeded(ValueError):
    """No new generation may start under the current spend ceiling."""


def positive(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("The USD limit must be a positive finite Decimal")
    return value


def pricing() -> dict[str, Any]:
    return json.loads((DATA / "model_pricing.json").read_text(encoding="utf-8"))


def model_profiles() -> list[dict[str, Any]]:
    data = pricing()
    return [
        dict(
            row,
            checked_at=data["checked_at"],
            source=data["source"],
            service_tier=data["service_tier"],
            unit=data["unit"],
        )
        for row in data["models"]
    ]


def profile_for(model: str) -> dict[str, Any]:
    for profile in model_profiles():
        if profile["id"] == model:
            return profile
    raise ValueError("Unsupported model profile")


def worst_cost(profile: dict[str, Any], input_tokens: int, max_output_tokens: int) -> Decimal:
    return (
        Decimal(input_tokens) * max(Decimal(profile["input"]), Decimal(profile["cache_write"]))
        + Decimal(max_output_tokens) * Decimal(profile["output"])
    ) / Decimal(1_000_000)


def usage_cost(profile: dict[str, Any], usage: dict[str, Any]) -> Decimal:
    """Cache writes are a distinct billed input bucket; reasoning is part of output."""
    details = usage["input_tokens_details"]
    counts = [
        usage["input_tokens"],
        usage["output_tokens"],
        details["cached_tokens"],
        details["cache_write_tokens"],
        usage["output_tokens_details"]["reasoning_tokens"],
    ]
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError("Incomplete or invalid provider usage")
    inputs, outputs, cached, writes, reasoning = counts
    if cached + writes > inputs or reasoning > outputs:
        raise ValueError("Inconsistent provider usage")
    return (
        Decimal(inputs - cached - writes) * Decimal(profile["input"])
        + Decimal(cached) * Decimal(profile["cached_input"])
        + Decimal(writes) * Decimal(profile["cache_write"])
        + Decimal(outputs) * Decimal(profile["output"])
    ) / Decimal(1_000_000)


class SessionBudget:
    def __init__(self, limit_usd: Decimal = Decimal("1")):
        self.limit_usd = positive(limit_usd)
        self.spent_usd = Decimal(0)
        self._reservations: dict[str, Decimal] = {}
        self._unknown: set[str] = set()
        self._unacknowledged: set[str] = set()
        self._lock = Lock()

    def _reserved(self) -> Decimal:
        return sum(self._reservations.values(), Decimal(0))

    def reserve(self, amount: Decimal) -> str:
        positive(amount)
        with self._lock:
            if self._unacknowledged or self.spent_usd + self._reserved() + amount > self.limit_usd:
                raise BudgetExceeded("Session budget or unresolved usage blocks generation")
            token = uuid4().hex
            self._reservations[token] = amount
            return token

    def settle(self, token: str, actual: Decimal) -> None:
        if not actual.is_finite() or actual < 0:
            raise ValueError("Invalid actual cost")
        with self._lock:
            if token not in self._reservations:
                raise ValueError("Unknown reservation")
            del self._reservations[token]
            self._unknown.discard(token)
            self._unacknowledged.discard(token)
            self.spent_usd += actual

    def mark_unknown(self, token: str) -> None:
        with self._lock:
            if token not in self._reservations:
                raise ValueError("Unknown reservation")
            self._unknown.add(token)
            self._unacknowledged.add(token)

    def acknowledge_unknown(self) -> None:
        with self._lock:
            self._unacknowledged.clear()

    def set_limit(self, limit_usd: Decimal) -> None:
        positive(limit_usd)
        with self._lock:
            if limit_usd < self.spent_usd + self._reserved():
                raise ValueError("Limit cannot undercut charges and outstanding reservations")
            self.limit_usd = limit_usd

    def summary(self) -> dict[str, Any]:
        with self._lock:
            reserved = self._reserved()
            return {
                "limit_usd": str(self.limit_usd),
                "spent_usd": str(self.spent_usd),
                "reserved_usd": str(reserved),
                "remaining_usd": str(max(Decimal(0), self.limit_usd - self.spent_usd - reserved)),
                "unknown_cost": bool(self._unknown),
                "blocked": bool(self._unacknowledged),
            }
