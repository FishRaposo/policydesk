"""Synthetic extraction/drafting around real policy, validators and storage."""

from datetime import date
from typing import Any

from pydantic import ValidationError

from .models import Decision, DraftReply, Extraction, LookupOrderArguments, Order, Ticket, Violation
from .openai_client import ResponseClient, request
from .policy import evaluate
from .replies import render
from .resources import digest
from .store import Store
from .validators import check


def run(ticket: Ticket, store: Store, client: ResponseClient, today: date) -> dict[str, Any]:
    ticket_id = digest({"ticket": ticket.model_dump(mode="json"), "today": today.isoformat()})[:24]
    extract_request = request(
        "extract", ticket=ticket.model_dump(mode="json"), today=today.isoformat()
    )
    raw = client.call(extract_request)
    trace: list[dict[str, Any]] = [
        {"step": "extract", "provenance": "synthetic", "request_hash": digest(extract_request)}
    ]
    order: Order | None = None
    denied = False
    extraction: Extraction | None = None
    extraction_failure = False
    try:
        extraction = Extraction.model_validate(raw["extraction"])
        calls = raw.get("tool_calls", [])
        if not isinstance(calls, list) or len(calls) > 3:
            raise ValueError("At most three read-only tool calls")
        if extraction.language != ticket.language:
            raise ValueError("Extraction cannot change the trusted ticket language")
        seen: dict[str, Order] = {}
        ambiguous = False
        for call in calls:
            if call["name"] == "lookup_order" and set(call["arguments"]) == {"order_id"}:
                arguments = LookupOrderArguments.model_validate(call["arguments"])
                status, candidate = store.lookup(arguments.order_id, ticket.customer_id)
                denied = denied or status == "ownership_denied"
                if candidate:
                    seen[candidate.order_id] = candidate
                trace.append({"step": "lookup_order", "status": status})
            elif call["name"] == "list_recent_orders" and call["arguments"] == {}:
                recent = store.recent(ticket.customer_id)
                # M0 does not infer which of several orders a customer means.
                ambiguous = ambiguous or len(recent) != 1
                if len(recent) == 1:
                    seen[recent[0].order_id] = recent[0]
                trace.append(
                    {"step": "list_recent_orders", "status": "ambiguous" if ambiguous else "found"}
                )
            else:
                raise ValueError(
                    "Unknown tool or arguments; customer scope cannot come from a tool call"
                )
        order = seen.get(extraction.order_id or "") if not ambiguous else None
        decision = evaluate(extraction, order, ticket.customer_id, today, ownership_denied=denied)
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        extraction_failure = True
        decision = Decision(
            outcome="needs_human", actions=[], clause_ids=["XX-0"], reasons=["invalid_extraction"]
        )
        trace.append({"step": "extract_rejected", "reason": type(exc).__name__})

    trace.append({"step": "decide", "decision": decision.model_dump(mode="json")})
    attempts: list[dict[str, Any]] = []
    final: DraftReply | None = None
    violations: list[Violation] = []
    if not extraction_failure:
        for attempt in range(2):
            draft_request = request(
                "draft" if attempt == 0 else "repair",
                language=ticket.language,
                ticket_hash=digest(ticket.model_dump(mode="json")),
                decision=decision.model_dump(mode="json"),
                violations=[v.code for v in violations] if attempt else [],
            )
            response = client.call(draft_request)
            try:
                draft = DraftReply.model_validate(response)
                violations = check(draft, decision, ticket.language)
            except (ValidationError, ValueError):
                draft = None
                violations = [Violation(code="schema", detail="Invalid structured draft")]
            attempts.append(
                {
                    "step": "draft" if attempt == 0 else "repair",
                    "provenance": "synthetic",
                    "request_hash": digest(draft_request),
                    "violations": [v.model_dump() for v in violations],
                }
            )
            if not violations:
                final = draft
                break
    if final is None:
        original = decision.model_dump(mode="json")
        decision = Decision(
            outcome="needs_human",
            actions=[],
            clause_ids=decision.clause_ids,
            reasons=["invalid_extraction" if extraction_failure else "validation_failed"],
        )
        final = render(decision, ticket.language)
        violations = check(final, decision, ticket.language)
        if violations:
            raise ValueError("Internal handoff template failed validation")
        trace.append({"step": "handoff", "proposed_decision": original})
    trace.extend(attempts)
    pending = (
        store.create_pending(ticket_id, order, decision, ticket.customer_id, today) if order else []
    )
    result = {
        "ticket_id": ticket_id,
        "provenance": "synthetic",
        "decision": decision.model_dump(mode="json"),
        "extraction": extraction.model_dump(mode="json") if extraction else None,
        "reply": final.model_dump(mode="json"),
        "violations": [v.model_dump() for v in violations],
        "pending_actions": pending,
        "trace": trace,
        "repair_attempted": len(attempts) == 2,
        "api_cost_usd": None,
        "model_latency_ms": None,
        "cached_input_share": None,
    }
    store.audit(ticket_id, "result", result)
    return result
