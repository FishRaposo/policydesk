"""Typed fixture access; reserved cases are read only by evaluation tooling."""

import hashlib
import json
from typing import Any

import yaml

from .models import Order, Ticket
from .resources import DATA


def orders() -> list[Order]:
    return [
        Order.model_validate(o)
        for o in yaml.safe_load((DATA / "orders.yaml").read_text(encoding="utf-8"))
    ]


def cases(split: str = "dev") -> list[dict[str, Any]]:
    if split not in ("dev", "heldout"):
        raise ValueError("Split must be dev or heldout")
    if split == "heldout":
        check_reserved_hash()
    return [
        json.loads(line)
        for line in (DATA / "cases" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def check_reserved_hash() -> str:
    actual = hashlib.sha256((DATA / "cases/heldout.jsonl").read_bytes()).hexdigest()
    if actual != (DATA / "cases/heldout.sha256").read_text(encoding="utf-8").strip():
        raise ValueError("Reserved case SHA-256 changed; do not overwrite the frozen hash")
    return actual


def ticket_for(case: dict[str, Any]) -> Ticket:
    return Ticket(customer_id=case["customer_id"], language=case["lang"], message=case["message"])
