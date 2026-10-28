"""Catch replay substitution, foreign context leaks, excessive repair and stale approval."""

import json
from datetime import date

import pytest

from policydesk.fixtures import cases, orders, ticket_for
from policydesk.models import TODAY
from policydesk.openai_client import (
    CassetteInvalid,
    CassetteMissing,
    NetworkModeDisabled,
    ReplayClient,
    request,
)
from policydesk.pipeline import run
from policydesk.resources import DATA, digest
from policydesk.store import StaleApproval, Store


@pytest.fixture()
def store(tmp_path):
    value = Store(tmp_path / "test.db")
    value.seed(orders())
    yield value
    value.close()


@pytest.mark.parametrize("mode", ["live", "record", "typo"])
def test_network_modes_fail_before_any_transport(mode):
    with pytest.raises(NetworkModeDisabled):
        ReplayClient(mode=mode)


def test_unknown_request_never_falls_back():
    with pytest.raises(CassetteMissing):
        ReplayClient().call(request("extract", message="unknown"))


@pytest.mark.parametrize(
    "mutation", ["payload", "key", "version", "provenance", "extra", "malformed"]
)
def test_tampered_cassette_is_rejected(tmp_path, mutation):
    ticket = ticket_for(cases()[0])
    payload = request("extract", ticket=ticket.model_dump(mode="json"), today=TODAY.isoformat())
    name = f"{digest(payload)}.json"
    envelope = json.loads((DATA / "cassettes" / name).read_text(encoding="utf-8"))
    if mutation == "payload":
        envelope["response"]["extraction"]["claim"] = "none"
    elif mutation == "key":
        envelope["request_hash"] = "wrong"
    elif mutation == "version":
        envelope["schema_version"] = 2
    elif mutation == "provenance":
        envelope["provenance"] = "recorded"
    elif mutation == "extra":
        envelope["fake_usage"] = 123
    (tmp_path / name).write_text(
        "{" if mutation == "malformed" else json.dumps(envelope), encoding="utf-8"
    )
    with pytest.raises(CassetteInvalid):
        ReplayClient(tmp_path).call(payload)


def test_repair_is_one_attempt_then_handoff(store):
    dev = cases()
    repaired = run(ticket_for(dev[4]), store, ReplayClient(), TODAY)
    assert repaired["decision"]["outcome"] == "approve"
    assert [s["step"] for s in repaired["trace"]].count("repair") == 1
    refused = run(ticket_for(dev[5]), store, ReplayClient(), TODAY)
    assert refused["decision"]["outcome"] == "needs_human"
    assert refused["pending_actions"] == []
    assert [s["step"] for s in refused["trace"]].count("repair") == 1


def test_foreign_tool_record_never_enters_output_or_audit(store):
    status, value = store.lookup("GN-1009", "C-01")
    assert status == "ownership_denied" and value is None
    result = run(ticket_for(cases()[3]), store, ReplayClient(), TODAY)
    assert result["decision"]["clause_ids"] == ["ID-1"]
    assert result["pending_actions"] == []
    assert "Fictional coffee" not in json.dumps(result)
    assert "Fictional coffee" not in json.dumps(store.history())


def test_approval_is_authorization_only_and_idempotent(store):
    result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
    action_id = result["pending_actions"][0]["id"]
    assert store.approve(action_id, "local-operator", TODAY) == {
        "id": action_id,
        "status": "approved",
        "executed": False,
        "already_approved": False,
    }
    assert store.approve(action_id, "another-label", TODAY)["already_approved"] is True
    assert sum(row["step"] == "approval" for row in store.history()) == 1
    assert store.lookup("GN-1007", "C-01")[1] == next(
        o for o in orders() if o.order_id == "GN-1007"
    )


@pytest.mark.parametrize("approved_first", [False, True])
def test_order_edit_invalidates_pending_and_already_approved_action(store, approved_first):
    result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
    action_id = result["pending_actions"][0]["id"]
    if approved_first:
        store.approve(action_id, "operator", TODAY)
    original = next(o for o in orders() if o.order_id == "GN-1007")
    store.put_order(original.model_copy(update={"shipping_fee": original.shipping_fee + 1}))
    with pytest.raises(StaleApproval):
        store.approve(action_id, "operator", TODAY)
    assert (
        store.connection.execute(
            "SELECT status FROM pending_actions WHERE id=?", (action_id,)
        ).fetchone()["status"]
        == "stale"
    )


def test_changed_date_invalidates_action(store):
    result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
    with pytest.raises(StaleApproval):
        store.approve(result["pending_actions"][0]["id"], "operator", date(2026, 11, 3))


def test_changed_policy_invalidates_action(store, monkeypatch):
    result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
    from policydesk.resources import load_policy

    monkeypatch.setattr("policydesk.store.load_policy", lambda: {**load_policy(), "version": "v2"})
    with pytest.raises(StaleApproval):
        store.approve(result["pending_actions"][0]["id"], "operator", TODAY)


def test_store_survives_restart(tmp_path):
    path = tmp_path / "restart.db"
    store = Store(path)
    store.seed(orders())
    result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
    store.close()
    restarted = Store(path)
    try:
        assert restarted.history()[0]["payload"] == result
        assert (
            restarted.approve(result["pending_actions"][0]["id"], "operator", TODAY)["executed"]
            is False
        )
    finally:
        restarted.close()


class SyntheticBoundary:
    """Explicit provider double; policy, scoping, validation and storage remain real."""

    def __init__(self, raw):
        self.raw = raw

    def call(self, payload):
        if payload["step"] == "extract":
            return self.raw
        from policydesk.models import Decision
        from policydesk.replies import render

        return render(Decision.model_validate(payload["decision"]), payload["language"]).model_dump(
            mode="json"
        )


def test_ambiguous_recent_orders_cannot_authorize(store):
    case = cases()[0]
    client = SyntheticBoundary(
        {
            "extraction": case["extraction"],
            "tool_calls": [{"name": "list_recent_orders", "arguments": {}}],
        }
    )
    result = run(ticket_for(case), store, client, TODAY)
    assert result["decision"]["outcome"] == "needs_human"
    assert result["pending_actions"] == []
    assert {"step": "list_recent_orders", "status": "ambiguous"} in result["trace"]


@pytest.mark.parametrize(
    "calls",
    [
        [{"name": "lookup_order", "arguments": {"order_id": "GN-1007", "customer_id": "C-OTHER"}}],
        [{"name": "refund", "arguments": {"order_id": "GN-1007"}}],
        [{"name": "list_recent_orders", "arguments": {}}] * 4,
    ],
)
def test_invalid_tool_arguments_or_excess_rounds_hand_off(store, calls):
    case = cases()[0]
    result = run(
        ticket_for(case),
        store,
        SyntheticBoundary({"extraction": case["extraction"], "tool_calls": calls}),
        TODAY,
    )
    assert result["decision"]["outcome"] == "needs_human"
    assert result["pending_actions"] == []
    assert result["decision"]["reasons"] == ["invalid_extraction"]
