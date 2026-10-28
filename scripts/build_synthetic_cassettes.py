"""One-time construction of labeled synthetic responses; never API recordings.

Reads reserved labels: the resulting report is author-known regression evidence.
Cannot overwrite existing cassettes. Changes require a new fixture protocol/version.
"""

import argparse
from pathlib import Path

from policydesk.fixtures import cases, orders, ticket_for
from policydesk.models import Decision
from policydesk.openai_client import request
from policydesk.replies import render
from policydesk.resources import DATA, canonical, digest


def write(directory: Path, payload: dict, response: dict) -> None:
    envelope = {
        "schema_version": 1,
        "provenance": "synthetic",
        "request_hash": digest(payload),
        "response": response,
    }
    envelope["integrity"] = digest(envelope)
    path = directory / f"{digest(payload)}.json"
    text = canonical(envelope) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise ValueError(f"Conflicting fixture for {path.name}")
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DATA / "cassettes")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Refusing to overwrite existing cassettes")
    args.output.mkdir(parents=True, exist_ok=True)
    by_id = {o.order_id: o for o in orders()}
    for case in [*cases("heldout"), *cases("dev")]:
        ticket = ticket_for(case)
        write(
            args.output,
            request("extract", ticket=ticket.model_dump(mode="json"), today="2026-11-02"),
            {"extraction": case["extraction"], "tool_calls": case["tool_calls"]},
        )
        expected = case["expected"]
        outcome = expected["outcome"]
        clauses = expected["clause_ids"]
        reasons = {
            "approve": "pending_confirmation",
            "deny": "outside_window",
            "needs_human": "unsupported_intent",
        }
        reason = (
            "ownership_denied"
            if clauses == ["ID-1"]
            else "refund_over_limit"
            if "LM-1" in clauses
            else reasons[outcome]
        )
        decision = Decision.model_validate({**expected, "reasons": [reason]})
        if case["fault"] == "handoff":
            order = by_id[case["extraction"]["order_id"]]
            decision = Decision.model_validate(
                {
                    "outcome": "approve",
                    "actions": [
                        {
                            "kind": "refund",
                            "order_id": order.order_id,
                            "amount": str(order.subtotal + order.shipping_fee),
                            "currency": order.currency,
                            "subscription_id": None,
                        }
                    ],
                    "clause_ids": ["RF-2"],
                    "reasons": ["pending_confirmation"],
                }
            )
        good = render(decision, ticket.language).model_dump(mode="json")
        first = {**good, "stated_amount": "99999.00"} if case["fault"] else good
        common = {
            "language": ticket.language,
            "ticket_hash": digest(ticket.model_dump(mode="json")),
            "decision": decision.model_dump(mode="json"),
        }
        write(args.output, request("draft", **common, violations=[]), first)
        if case["fault"]:
            write(
                args.output,
                request("repair", **common, violations=["amount_matches"]),
                first if case["fault"] == "handoff" else good,
            )
    print(
        f"Created {len(list(args.output.glob('*.json')))} SYNTHETIC cassettes. No model calls or usage measurements."
    )


if __name__ == "__main__":
    main()
