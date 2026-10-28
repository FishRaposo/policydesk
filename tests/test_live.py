"""Live SDK boundaries are exercised only through intercepted fake-key HTTP."""

import asyncio
import importlib.util
import json
import logging
import os
from decimal import Decimal

import httpx
import pytest

from policydesk.fixtures import orders
from policydesk.models import Ticket
from policydesk.store import Store


def run_async(coroutine):
    return asyncio.run(coroutine)


def response(output, usage=None):
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 1793145600,
        "model": "gpt-6-luna",
        "service_tier": "default",
        "status": "completed",
        "output": output,
        "usage": usage
        or {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


def message(value):
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": json.dumps(value), "annotations": []}],
    }


def test_sdk_extraction_policy_and_reply_tracer(tmp_path):
    # A missing provider is a missing executable behavior, reported as an assertion.
    assert importlib.util.find_spec("policydesk.live") is not None, "Responses workflow is absent"
    from policydesk.live import OpenAIProvider
    from policydesk.models import Extraction
    from policydesk.policy import evaluate
    from policydesk.replies import render
    from policydesk.telemetry import SessionBudget

    order = orders()[0]
    ticket = Ticket(
        customer_id=order.customer_id,
        language="en",
        message=f"Refund {order.order_id}; changed my mind.",
    )
    extraction = Extraction(
        language="en",
        intent="refund_request",
        order_id=order.order_id,
        claim="changed_mind",
        customer_stated_amount=None,
    )
    from policydesk.models import TODAY

    decision = evaluate(extraction, order, ticket.customer_id, TODAY)
    bodies = []
    outputs = [
        [
            {"type": "reasoning", "id": "rs_mock", "summary": [], "encrypted_content": "cipher"},
            {
                "type": "function_call",
                "id": "fc_mock",
                "call_id": "call_mock",
                "name": "lookup_order",
                "arguments": json.dumps({"order_id": order.order_id}),
            },
        ],
        [message(extraction.model_dump(mode="json"))],
        [message(render(decision, "en").model_dump(mode="json"))],
    ]

    def handler(request):
        assert request.url.host == "api.openai.com"
        body = json.loads(request.content)
        bodies.append((request.url.path, body))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": 100}
            )
        return httpx.Response(200, json=response(outputs.pop(0)))

    async def exercise():
        provider = OpenAIProvider(
            "fakekey", SessionBudget(Decimal("1")), transport=httpx.MockTransport(handler)
        )
        store = Store(tmp_path / "db.sqlite")
        store.seed(orders())
        try:
            return await provider.run(ticket, store)
        finally:
            await provider.aclose()
            store.close()

    result = run_async(exercise())
    assert result["status"] == "completed"
    assert result["decision"] == decision.model_dump(mode="json")
    assert result["provenance"] == "mock_openai_transport"
    assert len(result["calls"]) == 6  # three counts plus three generations
    generations = [body for path, body in bodies if not path.endswith("input_tokens")]
    assert all(body["store"] is False for body in generations)
    assert all(body["max_output_tokens"] == 2048 for body in generations)
    assert all(body["reasoning"] == {"effort": "low"} for body in generations)
    assert any(item.get("encrypted_content") == "cipher" for item in generations[1]["input"])
    assert any(
        item.get("call_id") == "call_mock" and item["type"] == "function_call_output"
        for item in generations[1]["input"]
    )
    assert ticket.message in json.dumps(generations[2]["input"])
    assert result["metrics"]["estimated_cost_usd"] is not None
    assert result["metrics"]["ttft_ms"] is None


def tool(name="lookup_order", args=None, call_id="call_1"):
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args if args is not None else {"order_id": "GN-1001"}),
    }


def extracted(**updates):
    return {
        "language": "en",
        "intent": "refund_request",
        "order_id": "GN-1001",
        "claim": "changed_mind",
        "customer_stated_amount": None,
        **updates,
    }


def approved_reply(**updates):
    return {
        "body": "Your request meets the fictional policy. Proposed refund, pending human confirmation: BRL 79.90. No action has been executed.",
        "cited_clause_ids": ["RF-1"],
        "stated_amount": "79.90",
        "stated_currency": "BRL",
        "next_step": "refund_pending_confirmation",
        **updates,
    }


def execute(
    tmp_path,
    outputs,
    *,
    count=100,
    cap=Decimal("0.05"),
    session=None,
    handler_override=None,
    record=False,
    baseline=False,
    cancelled=None,
):
    from policydesk.live import OpenAIProvider
    from policydesk.telemetry import SessionBudget

    observed = []
    session = session or SessionBudget()

    def handler(request):
        body = json.loads(request.content)
        observed.append((request.url.path, body))
        if handler_override:
            custom = handler_override(request, body)
            if custom is not None:
                return custom
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": count}
            )
        output = outputs.pop(0)
        return httpx.Response(
            200,
            json=output if isinstance(output, dict) else response(output),
            headers={"x-request-id": "request-mock"},
        )

    async def exercise():
        provider = OpenAIProvider("fakekey", session, transport=httpx.MockTransport(handler))
        assert observed == []  # no startup/models/token-count calls
        store = Store(tmp_path / "workflow.sqlite")
        store.seed(orders())
        try:
            method = provider.baseline if baseline else provider.run
            result = await method(
                Ticket(
                    customer_id="C-01", language="en", message="Refund GN-1001; changed my mind."
                ),
                store,
                max_cost_usd=cap,
                record_dir=tmp_path / ".runtime" if record else None,
                cancelled=cancelled,
            )
            return result, observed, session
        finally:
            await provider.aclose()
            store.close()

    return run_async(exercise())


def test_recording_redacts_credentials_in_values_and_mapping_keys(tmp_path):
    raw = response([tool()])
    raw["fakekey"] = {"echo": "fakekey", "authorization": "Bearer fakekey"}
    result, _, _ = execute(
        tmp_path, [raw, [message(extracted())], [message(approved_reply())]], record=True
    )
    recording = next((tmp_path / ".runtime").glob("*.json"))
    text = recording.read_text(encoding="utf-8")
    assert "fakekey" not in text
    assert "authorization" not in text.casefold()
    from policydesk.live import replay_recording

    replay = replay_recording(recording)
    assert replay["recording_provenance"] == "mock_openai_transport"
    assert replay["metrics"] == result["metrics"]


def test_baseline_is_one_generation_with_only_preloaded_authorized_facts(tmp_path):
    decision = {
        "outcome": "approve",
        "actions": [
            {
                "kind": "refund",
                "order_id": "GN-1001",
                "amount": "79.90",
                "currency": "BRL",
                "subscription_id": None,
            }
        ],
        "clause_ids": ["RF-1"],
        "policy_version": "v1",
        "reasons": ["pending_confirmation"],
    }
    result, observed, _ = execute(
        tmp_path, [[message({"decision": decision, "reply": approved_reply()})]], baseline=True
    )
    assert result["status"] == "completed"
    assert result["pending_actions"] == []
    assert result["extraction"] is None
    assert len(observed) == 2
    generation = observed[-1][1]
    assert "tools" not in generation
    payload = json.loads(generation["input"][0]["content"])
    assert payload["authorized_orders"]
    assert all(order["customer_id"] == "C-01" for order in payload["authorized_orders"])
    assert all(order["customer_id"] != "C-02" for order in payload["authorized_orders"])
    assert "RF-1" in generation["instructions"]


def test_invalid_reply_is_repaired_once_with_actual_ticket_and_rejected_draft(tmp_path):
    bad = approved_reply(body="I have refunded BRL 999.00.", stated_amount="999.00")
    result, observed, _ = execute(
        tmp_path, [[tool()], [message(extracted())], [message(bad)], [message(approved_reply())]]
    )
    assert result["status"] == "completed"
    assert result["repair_attempted"] is True
    assert len(result["pending_actions"]) == 1
    repair = observed[-1][1]
    payload = json.loads(repair["input"][0]["content"])
    assert payload["ticket"]["message"] == "Refund GN-1001; changed my mind."
    assert payload["rejected_draft"] == bad
    assert "amount_matches" in [v["code"] for v in payload["violations"]]
    assert result["decision"]["actions"][0]["amount"] == "79.90"


def test_failed_repair_preserves_failure_and_hands_off_without_actions(tmp_path):
    bad = approved_reply(stated_amount="999.00")
    result, observed, _ = execute(
        tmp_path, [[tool()], [message(extracted())], [message(bad)], [message(bad)]]
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "reply_validation_failed"
    assert result["repair_attempted"] is True
    assert result["decision"]["outcome"] == "needs_human"
    assert result["pending_actions"] == []
    assert result["decision"]["actions"] == []
    assert result["violations"]
    assert len([path for path, _ in observed if not path.endswith("input_tokens")]) == 4


def test_foreign_lookup_returns_no_record_and_immediate_safe_handoff(tmp_path):
    foreign = next(o for o in orders() if o.customer_id != "C-01")
    result, observed, _ = execute(tmp_path, [[tool(args={"order_id": foreign.order_id})]])
    assert result["status"] == "completed"
    assert result["decision"]["clause_ids"] == ["ID-1"]
    assert result["reply"]["next_step"] == "handed_off"
    assert foreign.order_id not in result["reply"]["body"]
    assert result["pending_actions"] == []
    assert len(observed) == 2
    assert foreign.customer_id not in json.dumps(observed)


@pytest.mark.parametrize(
    "calls",
    [
        [tool(args={"order_id": "GN-1001", "customer_id": "C-02"})],
        [tool(name="refund")],
        [tool(call_id=f"call_{i}") for i in range(4)],
    ],
)
def test_tools_reject_customer_scope_mutation_and_excess_calls(tmp_path, calls):
    result, observed, _ = execute(tmp_path, [calls])
    assert result["status"] == "failed"
    assert result["decision"]["outcome"] == "needs_human"
    assert result["pending_actions"] == []
    assert len(observed) == 2


def test_reused_tool_call_ids_are_rejected_across_rounds(tmp_path):
    result, observed, _ = execute(tmp_path, [[tool()], [tool()]])
    assert result["error_code"] == "invalid_tool_call_id"
    assert result["pending_actions"] == []
    assert len(observed) == 4


def test_three_readonly_calls_max_and_six_total_generations(tmp_path):
    bad = approved_reply(stated_amount="999.00")
    outputs = [[tool(call_id=f"call_{i}")] for i in range(3)]
    outputs += [[message(extracted())], [message(bad)], [message(approved_reply())]]
    result, observed, _ = execute(tmp_path, outputs)
    assert result["status"] == "completed"
    assert len([path for path, _ in observed if not path.endswith("input_tokens")]) == 6
    assert len(result["calls"]) == 12


def test_preflight_input_ceiling_rejects_before_generation(tmp_path):
    result, observed, session = execute(tmp_path, [], count=32001)
    assert result["error_code"] == "input_token_limit"
    assert len(observed) == 1
    assert result["metrics"]["estimated_cost_usd"] == "0"
    assert session.summary()["reserved_usd"] == "0"


def test_reservation_blocks_generation_before_spend(tmp_path):
    result, observed, _ = execute(tmp_path, [], cap=Decimal("0.000001"))
    assert result["status"] == "budget_exceeded"
    assert result["error_code"] == "run_budget_exceeded"
    assert len(observed) == 1


def test_timeout_is_not_retried_and_holds_unknown_charge(tmp_path):
    def timeout(request, _body):
        if not request.url.path.endswith("input_tokens"):
            raise httpx.ReadTimeout("provider echoed fakekey", request=request)

    result, observed, session = execute(tmp_path, [], handler_override=timeout)
    assert result["status"] == "failed"
    assert len(observed) == 2  # one free preflight, one attempt, no SDK retry
    assert result["metrics"]["estimated_cost_usd"] is None
    assert result["metrics"]["unknown_cost"] is True
    assert session.summary()["blocked"] is True
    assert Decimal(session.summary()["reserved_usd"]) > 0
    assert "fakekey" not in json.dumps(result)
    assert result["calls"][-1]["unknown_cost"] is True
    result2, observed2, _ = execute(tmp_path, [], session=session)
    assert result2["status"] == "budget_exceeded"
    assert observed2 == []


def test_missing_usage_is_unknown_and_does_not_continue(tmp_path):
    raw = response([tool()])
    raw.pop("usage")
    result, observed, session = execute(tmp_path, [raw])
    assert result["error_code"] == "unknown_provider_usage"
    assert len(observed) == 2
    assert session.summary()["unknown_cost"] is True
    assert result["pending_actions"] == []


def test_http_rejection_is_recorded_without_retry_and_missing_usage_remains_unknown(tmp_path):
    def rejected(request, _body):
        if not request.url.path.endswith("input_tokens"):
            return httpx.Response(
                401, json={"error": {"message": "echo fakekey", "type": "invalid_api_key"}}
            )

    result, observed, session = execute(tmp_path, [], handler_override=rejected)
    assert len(observed) == 2
    assert result["metrics"]["estimated_cost_usd"] is None
    assert result["metrics"]["unknown_cost"] is True
    assert Decimal(session.summary()["reserved_usd"]) > 0
    assert result["calls"][-1]["http_status"] == 401
    assert "fakekey" not in json.dumps(result)


def test_attempts_report_requested_and_returned_metadata_without_inference(tmp_path):
    result, _, _ = execute(
        tmp_path, [[tool()], [message(extracted())], [message(approved_reply())]]
    )
    for call in result["calls"]:
        assert call["requested_model"] == "gpt-6-luna"
        assert call["sdk_version"] == "2.54.0"
        assert call["prompt_version"]
        assert all(
            len(call[field]) == 64 for field in ("prompt_hash", "schema_hash", "source_hash")
        )
        if call["kind"] == "generation":
            assert call["returned_model"] == "gpt-6-luna"
            assert call["requested_service_tier"] == "default"
            assert call["returned_service_tier"] == "default"
            assert call["request_id"] == "request-mock"
        else:
            assert call["returned_model"] is None
            assert call["requested_service_tier"] is None
            assert call["returned_service_tier"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "gpt-6.1-terra"),
        ("model", None),
        ("service_tier", "priority"),
        ("service_tier", None),
    ],
)
def test_unknown_returned_billing_profile_is_never_priced_using_selected_rates(
    tmp_path, field, value
):
    raw = response([tool()])
    raw[field] = value
    result, observed, session = execute(tmp_path, [raw])
    assert result["status"] == "failed"
    assert result["error_code"] == "unexpected_billing_profile"
    assert result["metrics"]["estimated_cost_usd"] is None
    assert result["metrics"]["unknown_cost"] is True
    assert session.summary()["spent_usd"] == "0"
    assert Decimal(session.summary()["reserved_usd"]) > 0
    assert session.summary()["blocked"] is True
    assert len(observed) == 2


def test_quota_error_preserves_unknown_reservation_and_request_identifier(tmp_path):
    def quota(request, _body):
        if not request.url.path.endswith("input_tokens"):
            return httpx.Response(
                429,
                json={"error": {"message": "fake quota", "type": "insufficient_quota"}},
                headers={"x-request-id": "quota-request-id"},
            )

    result, observed, session = execute(tmp_path, [], handler_override=quota)
    assert len(observed) == 2
    assert result["metrics"]["estimated_cost_usd"] is None
    assert result["metrics"]["unknown_cost"] is True
    assert session.summary()["blocked"] is True
    assert result["calls"][-1]["http_status"] == 429
    assert result["calls"][-1]["request_id"] == "quota-request-id"


def test_token_count_error_records_available_identifiers_and_null_returned_metadata(tmp_path):
    def rejected_count(request, _body):
        return httpx.Response(
            503,
            json={"error": {"message": "count unavailable"}},
            headers={"x-request-id": "count-request-id"},
        )

    result, observed, _ = execute(tmp_path, [], handler_override=rejected_count)
    assert len(observed) == 1
    call = result["calls"][0]
    assert call["kind"] == "input_token_count"
    assert call["request_id"] == "count-request-id"
    assert call["http_status"] == 503
    assert call["returned_model"] is None
    assert call["returned_service_tier"] is None
    assert call["requested_model"] == "gpt-6-luna"
    assert call["sdk_version"] == "2.54.0"


def test_cancellation_before_run_does_not_make_any_request(tmp_path):
    result, observed, _ = execute(tmp_path, [], cancelled=lambda: True)
    assert result["status"] == "cancelled"
    assert result["pending_actions"] == []
    assert observed == []


def test_recording_tampering_is_loud_and_original_timestamps_are_preserved(tmp_path):
    from policydesk.live import replay_recording

    result, _, _ = execute(
        tmp_path, [[tool()], [message(extracted())], [message(approved_reply())]], record=True
    )
    target = next((tmp_path / ".runtime").glob("*.json"))
    assert replay_recording(target)["metrics"]["measured_at"] == result["metrics"]["measured_at"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["result"]["decision"]["outcome"] = "deny"
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        replay_recording(target)


def test_capture_requests_equal_each_actual_http_body_before_history_continuations(tmp_path):
    _, observed, _ = execute(
        tmp_path, [[tool()], [message(extracted())], [message(approved_reply())]], record=True
    )
    recording = json.loads(next((tmp_path / ".runtime").glob("*.json")).read_text(encoding="utf-8"))
    exchanges = recording["exchanges"]
    assert len(exchanges) == len(observed)
    for exchange, (path, actual_body) in zip(exchanges, observed, strict=True):
        assert exchange["request"] == actual_body, (
            f"Captured request changed after issuance: {path}"
        )


def test_runtime_recording_works_under_a_checkout_parent_named_src(tmp_path):
    checkout = tmp_path / "src" / "checkout"
    checkout.mkdir(parents=True)
    result, _, _ = execute(
        checkout, [[tool()], [message(extracted())], [message(approved_reply())]], record=True
    )
    assert result["status"] == "completed"


def test_ambient_sdk_debug_logs_do_not_emit_ticket_payloads(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("OPENAI_LOG", "debug")
    caplog.set_level(logging.DEBUG, logger="openai._base_client")
    caplog.set_level(logging.DEBUG, logger="httpx")
    execute(tmp_path, [[tool()], [message(extracted())], [message(approved_reply())]])
    assert "Refund GN-1001; changed my mind." not in caplog.text
    assert "Request options:" not in caplog.text


def test_explicit_key_is_the_only_authorization_despite_ambient_sdk_custom_headers(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "OPENAI_CUSTOM_HEADERS",
        "Authorization: Bearer ambient-fake-key\nauthorization: Bearer ambient-lowercase-key\nX-Secret: ambient-fake-data",
    )
    observed = []

    def inspect_headers(request, _body):
        observed.append(dict(request.headers))

    execute(
        tmp_path,
        [[tool()], [message(extracted())], [message(approved_reply())]],
        handler_override=inspect_headers,
    )
    assert observed
    assert all(headers["authorization"] == "Bearer fakekey" for headers in observed)
    assert all("x-secret" not in headers for headers in observed)


def test_strict_wire_schemas_keep_all_object_properties_required_without_domain_keywords():
    from policydesk.prompts import BASELINE_FORMAT, DRAFT_FORMAT, EXTRACT_FORMAT

    def validate(node):
        if isinstance(node, list):
            for value in node:
                validate(value)
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            assert not (
                {"minLength", "maxLength", "pattern", "default", "format", "title"} & set(node)
            )
            for value in node.values():
                validate(value)

    for schema in (BASELINE_FORMAT, DRAFT_FORMAT, EXTRACT_FORMAT):
        validate(schema["format"]["schema"])


def test_all_strict_schema_references_resolve_from_the_schema_root():
    from policydesk.prompts import BASELINE_FORMAT, DRAFT_FORMAT, EXTRACT_FORMAT

    def check_references(node, root):
        if isinstance(node, dict):
            if "$ref" in node:
                target = root
                for part in node["$ref"].removeprefix("#/").split("/"):
                    assert part in target, f"Unresolved root schema reference {node['$ref']}"
                    target = target[part]
            for child in node.values():
                check_references(child, root)
        elif isinstance(node, list):
            for child in node:
                check_references(child, root)

    for config in (BASELINE_FORMAT, DRAFT_FORMAT, EXTRACT_FORMAT):
        root = config["format"]["schema"]
        check_references(root, root)


def test_money_wire_fields_accept_strings_and_null_only():
    from policydesk.prompts import BASELINE_FORMAT, DRAFT_FORMAT, EXTRACT_FORMAT

    fields = [
        EXTRACT_FORMAT["format"]["schema"]["properties"]["customer_stated_amount"],
        DRAFT_FORMAT["format"]["schema"]["properties"]["stated_amount"],
        BASELINE_FORMAT["format"]["schema"]["$defs"]["ProposedAction"]["properties"]["amount"],
    ]
    assert all(field == {"anyOf": [{"type": "string"}, {"type": "null"}]} for field in fields)


def test_explicit_sdk_credentials_prevent_environment_credential_inference(monkeypatch):
    from policydesk.live import OpenAIProvider
    from policydesk.telemetry import SessionBudget

    environment_get = os.environ.get

    def guard(name, default=None):
        if name in {"OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "OPENAI_WEBHOOK_SECRET"}:
            raise AssertionError(f"Ambient credential access prohibited: {name}")
        return environment_get(name, default)

    monkeypatch.setattr(os.environ, "get", guard)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid/v1")

    async def exercise():
        provider = OpenAIProvider(
            "fakekey",
            SessionBudget(),
            transport=httpx.MockTransport(lambda _: pytest.fail("No startup requests")),
        )
        assert str(provider._client.base_url) == "https://api.openai.com/v1/"
        assert provider._client.max_retries == 0
        assert provider._client.timeout == 30
        await provider.aclose()
        assert provider._client.api_key == ""

    run_async(exercise())


def test_actual_async_request_deadline_holds_reservation(monkeypatch, tmp_path):
    from policydesk.live import OpenAIProvider
    from policydesk.telemetry import LIVE_LIMITS, SessionBudget

    observed = []

    async def slow_generation(request):
        observed.append(request.url.path)
        if request.url.path.endswith("input_tokens"):
            # Leave preflight startup unbounded by this tiny test deadline; shorten
            # only the next generation timeout so SDK module loading cannot race it.
            monkeypatch.setitem(LIVE_LIMITS, "request_timeout_seconds", 0.01)
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": 100}
            )
        await asyncio.sleep(1)
        pytest.fail("Generation should have been interrupted by request deadline")

    async def exercise():
        session = SessionBudget()
        provider = OpenAIProvider(
            "fakekey", session, transport=httpx.MockTransport(slow_generation)
        )
        store = Store(tmp_path / "deadline.sqlite")
        try:
            result = await provider.run(
                Ticket(customer_id="C-01", language="en", message="Refund GN-1001"), store
            )
            assert result["status"] == "failed"
            assert result["metrics"]["unknown_cost"] is True
            assert session.summary()["blocked"] is True
            assert len(observed) == 2
        finally:
            await provider.aclose()
            store.close()

    run_async(exercise())


def test_malformed_provider_output_fails_closed_with_known_usage(tmp_path):
    malformed = response([])
    malformed["output"] = {"unexpected": "object instead of array"}
    result, observed, _ = execute(tmp_path, [malformed])
    assert result["status"] == "failed"
    assert result["pending_actions"] == []
    assert result["decision"]["outcome"] == "needs_human"
    assert len(observed) == 2
    assert result["metrics"]["unknown_cost"] is False
