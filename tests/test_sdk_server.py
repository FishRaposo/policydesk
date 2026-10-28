"""Actual SDK parsing + ASGI + policy + authorization; HTTP is intercepted in memory."""

import json
import time

import httpx
from fastapi.testclient import TestClient

from policydesk.fixtures import cases
from policydesk.live import OpenAIProvider
from policydesk.models import Decision
from policydesk.replies import render
from policydesk.server import create_app


def test_sdk_asgi_policy_tracer_and_no_secret_in_http_or_artifacts(tmp_path):
    key = "sk-test-sdk-server-intercepted-only"
    origin = "http://127.0.0.1:8765"
    case = cases()[0]
    reply = render(Decision.model_validate({**case["expected"], "reasons": []}), case["lang"])
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": 500}
            )
        name = body["text"]["format"]["name"]
        if name == "extraction" and not any(
            i.get("type") == "function_call_output" for i in body["input"]
        ):
            output = [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "lookup_order",
                    "arguments": json.dumps({"order_id": case["extraction"]["order_id"]}),
                }
            ]
        else:
            payload = case["extraction"] if name == "extraction" else reply.model_dump(mode="json")
            output = [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": json.dumps(payload), "annotations": []}
                    ],
                }
            ]
        return httpx.Response(
            200,
            headers={"x-request-id": "req_mock_sdk"},
            json={
                "id": "resp_mock_sdk",
                "object": "response",
                "created_at": 1793145600,
                "status": "completed",
                "model": "gpt-6-luna",
                "service_tier": "default",
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
        assert api_key == key
        return OpenAIProvider(api_key, session, model=model, transport=httpx.MockTransport(handler))

    with TestClient(
        create_app(key, data_dir=tmp_path, provider_factory=factory), base_url=origin
    ) as client:
        config = client.get("/api/config").json()
        assert requests == []
        headers = {"Origin": origin, "X-PolicyDesk-CSRF": config["csrf_token"]}
        started = client.post(
            "/api/runs",
            headers=headers,
            json={
                "kind": "ticket",
                "revision": 0,
                "confirm_spend": True,
                "idempotency_key": "sdk-1",
            },
        )
        assert started.status_code == 202
        job_id = started.json()["id"]
        job = {}
        for _ in range(200):
            job = client.get(f"/api/runs/{job_id}").json()
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed", job
        assert job["result"]["decision"]["actions"] == case["expected"]["actions"]
        assert job["result"]["provenance"] == "mock_openai_transport"
        assert len(requests) == 6
        action_id = job["result"]["pending_actions"][0]["id"]
        approved = client.post(
            f"/api/approvals/{action_id}", headers=headers, json={"revision": 0, "run_id": job_id}
        )
        assert approved.status_code == 200
        assert approved.json()["executed"] is False
        assert key not in client.get(f"/api/runs/{job_id}/report").text
        for path in tmp_path.rglob("*.json"):
            assert key not in path.read_text(encoding="utf-8")
