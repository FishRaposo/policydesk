"""Loopback contract with fake credentials and a locally intercepted provider."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from policydesk.fixtures import cases, ticket_for
from policydesk.server import create_app

KEY = "sk-test-not-a-real-credential-server"
ORIGIN = "http://127.0.0.1:8765"


class Provider:
    constructed = 0
    delay = 0.0

    def __init__(self, api_key, session, model):
        assert api_key == KEY
        type(self).constructed += 1

    async def run(self, ticket, store, **kwargs):
        from policydesk.models import TODAY
        from policydesk.openai_client import ReplayClient
        from policydesk.pipeline import run

        await asyncio.sleep(self.delay)
        if kwargs["cancelled"]():
            return {"status": "cancelled", "provenance": "mock_openai_transport"}
        result = run(ticket, store, ReplayClient(), TODAY)
        result.update(status="completed", provenance="mock_openai_transport", metrics={})
        return result

    async def aclose(self):
        pass


@pytest.fixture
def client(tmp_path):
    Provider.constructed = 0
    Provider.delay = 0
    with TestClient(
        create_app(KEY, data_dir=tmp_path, provider_factory=Provider), base_url=ORIGIN
    ) as result:
        yield result


def headers(client):
    return {"Origin": ORIGIN, "X-PolicyDesk-CSRF": client.get("/api/config").json()["csrf_token"]}


def payload(client, **updates):
    return {
        "kind": "ticket",
        "revision": client.get("/api/config").json()["workspace_revision"],
        "model": "gpt-6-luna",
        "max_cost_usd": "0.05",
        "session_limit_usd": "1.00",
        "record": False,
        "confirm_spend": True,
        "idempotency_key": "test-submission-1",
        **updates,
    }


def wait(client, job_id):
    for _ in range(100):
        value = client.get(f"/api/runs/{job_id}").json()
        if value["status"] not in ("queued", "running"):
            return value
        time.sleep(0.01)
    pytest.fail("local mocked job did not complete")


def test_startup_is_network_free_and_never_exposes_key(client):
    config = client.get("/api/config")
    assert config.status_code == 200
    assert KEY not in config.text
    assert config.json()["enabled"] is True
    assert Provider.constructed == 0


@pytest.mark.parametrize(
    "origin,csrf", [(None, True), ("https://evil.example", True), (ORIGIN, False)]
)
def test_mutations_require_exact_origin_and_csrf(client, origin, csrf):
    security = headers(client)
    if origin is None:
        security.pop("Origin")
    else:
        security["Origin"] = origin
    if not csrf:
        security["X-PolicyDesk-CSRF"] = "wrong"
    response = client.post("/api/runs", json=payload(client), headers=security)
    assert response.status_code == 403
    assert Provider.constructed == 0


def test_dns_rebinding_and_unconfirmed_runs_are_rejected(client):
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 400
    response = client.post(
        "/api/runs", json=payload(client, confirm_spend=False), headers=headers(client)
    )
    assert response.status_code == 422
    assert Provider.constructed == 0


def test_thin_local_job_uses_policy_and_simulates_approval_only(client):
    case = next(c for c in cases() if c["id"] == "D-PT-01")
    response = client.post(
        "/api/workspace",
        json={"ticket": ticket_for(case).model_dump(mode="json"), "order": None},
        headers=headers(client),
    )
    assert response.status_code == 200
    request = payload(client)
    started = client.post("/api/runs", json=request, headers=headers(client))
    assert started.status_code == 202
    job = wait(client, started.json()["id"])
    assert job["status"] == "completed"
    result = job["result"]
    assert result["decision"]["outcome"] == "approve"
    assert result["provenance"] == "mock_openai_transport"
    action = result["pending_actions"][0]["id"]
    approval = client.post(
        f"/api/approvals/{action}",
        json={"revision": job["revision"], "run_id": job["id"]},
        headers=headers(client),
    )
    assert approval.json()["executed"] is False
    again = client.post("/api/runs", json=request, headers=headers(client))
    assert again.json()["id"] == job["id"]
    assert Provider.constructed == 1
    assert KEY not in client.get(f"/api/runs/{job['id']}/report?format=json").text


def test_new_workspace_makes_old_actions_stale(client):
    job = wait(
        client, client.post("/api/runs", json=payload(client), headers=headers(client)).json()["id"]
    )
    action = job["result"]["pending_actions"][0]["id"]
    config = client.get("/api/config").json()
    ticket = {**config["workspace"]["ticket"], "message": "Changed fictional ticket"}
    client.post("/api/workspace", json={"ticket": ticket, "order": None}, headers=headers(client))
    response = client.post(
        f"/api/approvals/{action}",
        json={"revision": job["revision"], "run_id": job["id"]},
        headers=headers(client),
    )
    assert response.status_code == 409
    assert client.get(f"/api/runs/{job['id']}").json()["stale"] is True


def test_workspace_edit_revokes_authorization_in_durable_store(client, tmp_path):
    from policydesk.models import TODAY
    from policydesk.store import StaleApproval, Store

    job = wait(
        client, client.post("/api/runs", json=payload(client), headers=headers(client)).json()["id"]
    )
    action = job["result"]["pending_actions"][0]["id"]
    config = client.get("/api/config").json()
    client.post(
        "/api/workspace",
        json={
            "ticket": {**config["workspace"]["ticket"], "message": "Changed fictional facts"},
            "order": None,
        },
        headers=headers(client),
    )
    store = Store(tmp_path / f"{job['id']}.sqlite")
    try:
        with pytest.raises(StaleApproval):
            store.approve(action, "local-cli", TODAY)
    finally:
        store.close()


def test_invalid_edit_invalidates_before_attempting_to_save_bad_facts(client, tmp_path):
    from policydesk.models import TODAY
    from policydesk.store import StaleApproval, Store

    job = wait(
        client, client.post("/api/runs", json=payload(client), headers=headers(client)).json()["id"]
    )
    action = job["result"]["pending_actions"][0]["id"]
    invalidated = client.post("/api/workspace/invalidate", json={}, headers=headers(client))
    assert invalidated.status_code == 200
    assert invalidated.json()["revision"] > job["revision"]
    invalid_save = client.post(
        "/api/workspace", json={"ticket": {}, "order": "not an order"}, headers=headers(client)
    )
    assert invalid_save.status_code == 422
    store = Store(tmp_path / f"{job['id']}.sqlite")
    try:
        with pytest.raises(StaleApproval):
            store.approve(action, "local-cli", TODAY)
    finally:
        store.close()


def test_only_one_active_job_and_cancel_is_idempotent(client):
    Provider.delay = 0.3
    first = client.post("/api/runs", json=payload(client), headers=headers(client)).json()
    second = client.post(
        "/api/runs", json=payload(client, idempotency_key="second"), headers=headers(client)
    )
    assert second.status_code == 409
    for _ in range(2):
        assert (
            client.post(
                f"/api/runs/{first['id']}/cancel", json={}, headers=headers(client)
            ).status_code
            == 200
        )
    assert wait(client, first["id"])["status"] == "cancelled"


def test_cancel_revokes_actions_from_worker_finishing_after_request(client, tmp_path, monkeypatch):
    from policydesk.models import TODAY
    from policydesk.openai_client import ReplayClient
    from policydesk.pipeline import run
    from policydesk.store import StaleApproval, Store

    async def late_worker(self, ticket, store, **kwargs):
        await asyncio.sleep(0.15)
        result = run(ticket, store, ReplayClient(), TODAY)
        return {**result, "status": "completed", "provenance": "mock_openai_transport"}

    monkeypatch.setattr(Provider, "run", late_worker)
    first = client.post("/api/runs", json=payload(client), headers=headers(client)).json()
    client.post(f"/api/runs/{first['id']}/cancel", json={}, headers=headers(client))
    job = wait(client, first["id"])
    assert job["status"] == "cancelled"
    store = Store(tmp_path / f"{job['id']}.sqlite")
    try:
        row = store.connection.execute("SELECT id FROM pending_actions LIMIT 1").fetchone()
        assert row is not None
        with pytest.raises(StaleApproval):
            store.approve(row["id"], "local-cli", TODAY)
    finally:
        store.close()


def test_cancel_arriving_just_after_completion_revokes_authorization(client, tmp_path):
    from policydesk.models import TODAY
    from policydesk.store import StaleApproval, Store

    job = wait(
        client, client.post("/api/runs", json=payload(client), headers=headers(client)).json()["id"]
    )
    action = job["result"]["pending_actions"][0]["id"]
    client.post(f"/api/runs/{job['id']}/cancel", json={}, headers=headers(client))
    store = Store(tmp_path / f"{job['id']}.sqlite")
    try:
        with pytest.raises(StaleApproval):
            store.approve(action, "local-cli", TODAY)
    finally:
        store.close()


def test_validation_does_not_echo_sensitive_extra_fields(client):
    response = client.post("/api/runs", json=payload(client, api_key=KEY), headers=headers(client))
    assert response.status_code == 422
    assert KEY not in response.text
    assert Provider.constructed == 0


def test_offline_server_has_no_provider_or_key_lookup(tmp_path):
    with TestClient(create_app(None, data_dir=tmp_path), base_url=ORIGIN) as client:
        assert client.get("/api/config").json()["enabled"] is False
        assert (
            client.post("/api/runs", json=payload(client), headers=headers(client)).status_code
            == 409
        )
