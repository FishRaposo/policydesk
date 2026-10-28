"""Browser acceptance fixture: real ASGI/SDK with in-memory mock HTTP only.

Not a product entrypoint. No environment switch or route can activate this fixture
in the packaged app. Its process denies every non-loopback connection and DNS call.
"""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path

import httpx
import uvicorn

import policydesk
from policydesk.fixtures import cases
from policydesk.live import OpenAIProvider
from policydesk.models import Decision
from policydesk.replies import render
from policydesk.server import create_app

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".runtime/browser-http"
os.environ["OPENAI_CUSTOM_HEADERS"] = ""
original_connect = socket.socket.connect
original_resolve = socket.getaddrinfo


def connect(sock, address):
    if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
        return original_connect(sock, address)
    raise AssertionError("Acceptance fixture forbids external connections")


def resolve(host, *args, **kwargs):
    if host not in {"127.0.0.1", "::1", "localhost", None}:
        raise AssertionError("Acceptance fixture forbids external DNS")
    return original_resolve(host, *args, **kwargs)


socket.socket.connect = connect
socket.getaddrinfo = resolve


def message(value):
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": json.dumps(value), "annotations": []}],
    }


async def handler(request):
    # Model a yielding network round trip so the ASGI loop can serve cancellation
    # while a mocked comparison is active. This delay is synthetic, not API latency.
    await asyncio.sleep(0.02)
    body = json.loads(request.content)
    if request.url.host != "api.openai.com":
        raise AssertionError("Unexpected SDK destination")
    if request.url.path.endswith("input_tokens"):
        return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 500})
    first = json.loads(body["input"][0]["content"])
    ticket = first["ticket"]
    case = next(
        (
            c
            for c in cases()
            if c["message"] == ticket["message"]
            and c["customer_id"] == ticket["customer_id"]
            and c["lang"] == ticket["language"]
        ),
        None,
    )
    name = body["text"]["format"]["name"]
    if name == "extraction":
        completed = sum(i.get("type") == "function_call_output" for i in body["input"])
        planned = case.get("tool_calls", []) if case else []
        if completed < len(planned):
            call = planned[completed]
            output = [
                {
                    "id": f"fc_{completed}",
                    "type": "function_call",
                    "call_id": f"call_{completed}",
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"]),
                }
            ]
        else:
            output = [
                message(
                    case["extraction"]
                    if case
                    else {
                        "language": ticket["language"],
                        "intent": "other",
                        "order_id": None,
                        "claim": "none",
                        "customer_stated_amount": None,
                    }
                )
            ]
    elif name == "baseline":
        decision = (
            Decision.model_validate({**case["expected"], "reasons": ["mock_fixture"]})
            if case
            else Decision(
                outcome="needs_human", actions=[], clause_ids=["XX-0"], reasons=["mock_fixture"]
            )
        )
        output = [
            message(
                {
                    "decision": decision.model_dump(mode="json"),
                    "reply": render(decision, ticket["language"]).model_dump(mode="json"),
                }
            )
        ]
    else:
        decision = Decision.model_validate(first["decision"])
        output = [message(render(decision, ticket["language"]).model_dump(mode="json"))]
    return httpx.Response(
        200,
        headers={"x-request-id": "req_mock_local_fixture"},
        json={
            "id": "resp_mock_local_fixture",
            "object": "response",
            "created_at": 1793145600,
            "model": body["model"],
            "service_tier": "default",
            "status": "completed",
            "output": output,
            "usage": {
                "input_tokens": 500,
                "output_tokens": 100,
                "total_tokens": 600,
                "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 100},
                "output_tokens_details": {"reasoning_tokens": 10},
            },
        },
    )


def factory(api_key, session, model):
    return OpenAIProvider(api_key, session, model=model, transport=httpx.MockTransport(handler))


if __name__ == "__main__":
    bundled = Path(policydesk.__file__).resolve().parent / "web_dist"
    if os.environ.get("POLICYDESK_TEST_EXPECT_INSTALLED") == "1":
        assert "site-packages" in bundled.parts, "Expected installed package, not source checkout"
    web = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else bundled
        if bundled.is_dir()
        else ROOT / "web/dist"
    )
    app = create_app("fake-local-sdk-key", data_dir=DATA_DIR, provider_factory=factory, web_dir=web)
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False, log_level="warning")
