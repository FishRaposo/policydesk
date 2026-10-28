"""Fake-provider benchmark controls; these tests are not provider evidence."""

import copy
import json
from collections import Counter
from decimal import Decimal
from typing import Any

import pytest

from policydesk.benchmark import compare, grade, recruiter_cases
from policydesk.models import Decision
from policydesk.replies import render


def run_offline(coroutine):
    """Drive immediate fake awaits without Windows asyncio's loopback socketpair."""
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    finally:
        coroutine.close()
    raise AssertionError("Fake provider unexpectedly required an event loop")


def test_recruiter_cases_have_one_real_gold_outcome_per_language():
    selected = recruiter_cases()
    assert len(selected) == 9
    assert Counter((c["lang"], c["expected"]["outcome"]) for c in selected) == {
        (language, outcome): 1
        for language in ("pt", "es", "en")
        for outcome in ("approve", "deny", "needs_human")
    }
    assert all(c["split"] == "dev" and c["fault"] is None for c in selected)
    assert [c["id"] for c in selected] == [
        "D-PT-01",
        "D-PT-02",
        "D-PT-03",
        "D-ES-01",
        "D-ES-02",
        "D-ES-03",
        "D-EN-01",
        "D-EN-02",
        "D-EN-03",
    ]


def answer(case, *, cost: str | None = "0.001", workflow=10):
    decision = Decision.model_validate({**case["expected"], "reasons": ["fake_label"]})
    return {
        "status": "completed",
        "provenance": "fake_provider",
        "decision": decision.model_dump(mode="json"),
        "reply": render(decision, case["lang"]).model_dump(mode="json"),
        "extraction": copy.deepcopy(case["extraction"]),
        "pending_actions": [],
        "violations": [],
        "repair_attempted": False,
        "calls": [{"provenance": "fake_provider"}],
        "metrics": {
            "estimated_cost_usd": cost,
            "unknown_cost": cost is None,
            "workflow_ms": workflow,
            "api_round_trip_ms": workflow - 2,
            "local_processing_ms": 2,
            "ttft_ms": None,
        },
    }


class FakeProvider:
    """No SDK/network; reports must preserve this explicit fake provenance."""

    model = "fake-model"
    session: Any = None

    def __init__(self, *, failure_at=None, unknown_at=None, cost="0.001"):
        self.calls = []
        self.failure_at = failure_at
        self.unknown_at = unknown_at
        self.cost = cost
        self.stores = []
        self.metadata = {
            "model": self.model,
            "settings": {"temperature": 0},
            "pricing": {"source": "fake_test_prices", "input": "1"},
        }

    def benchmark_metadata(self):
        return self.metadata

    async def invoke(self, system, ticket, store, **options):
        assert options["create_actions"] is False
        assert options["max_cost_usd"] > 0
        self.stores.append(store)
        self.calls.append((system, ticket, options))
        # Both real Store instances must expose the same scoped fixture facts.
        assert store.recent(ticket.customer_id)
        assert store.connection.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0] == 0
        if len(self.calls) == self.failure_at:
            raise RuntimeError("sensitive details must not enter reports")
        case = next(c for c in recruiter_cases() if c["message"] == ticket.message)
        return answer(
            case,
            cost=None if len(self.calls) == self.unknown_at else self.cost,
            workflow=len(self.calls),
        )

    async def run(self, ticket, store, **options):
        return await self.invoke("pipeline", ticket, store, **options)

    async def baseline(self, ticket, store, **options):
        return await self.invoke("baseline", ticket, store, **options)


def test_gold_grader_rejects_universal_handoff_and_self_consistent_wrong_money():
    case = recruiter_cases()[0]
    wrong = answer(case)
    wrong["decision"]["outcome"] = "needs_human"
    wrong["decision"]["actions"] = []
    wrong["reply"] = render(Decision.model_validate(wrong["decision"]), "pt").model_dump(
        mode="json"
    )
    assert grade(wrong, case).get("passed") is False
    assert grade(wrong, case).get("outcome_correct") is False
    assert "amount_matches" in grade(wrong, case).get("unsafe_codes", [])
    wrong = answer(case)
    wrong["decision"]["actions"][0]["amount"] = "1.00"
    wrong["reply"] = render(Decision.model_validate(wrong["decision"]), "pt").model_dump(
        mode="json"
    )
    assert grade(wrong, case).get("actions_correct") is False
    assert "body_money_matches" in grade(wrong, case).get("unsafe_codes", [])


def test_grade_measures_extraction_clauses_and_malformed_results():
    case = recruiter_cases()[0]
    result = answer(case)
    assert grade(result, case).get("passed") is True
    result["extraction"]["claim"] = "none"
    assert grade(result, case).get("extraction_correct") is False
    assert grade(result, case).get("primary_pass") is True
    result = answer(case)
    result["decision"]["clause_ids"] = []
    assert grade(result, case).get("clauses_correct") is False
    assert grade({"status": "failed", "reply": {}}, case).get("passed") is False


def test_baseline_extraction_is_unmeasured_and_gold_primary_grade_remains_common():
    case = recruiter_cases()[0]
    baseline = {**answer(case), "system": "baseline", "extraction": None}
    assert grade(baseline, case).get("extraction_correct") is None
    assert grade(baseline, case).get("primary_pass") is True
    baseline["decision"]["actions"][0]["amount"] = "1.00"
    assert grade(baseline, case).get("primary_pass") is False


def test_default_comparison_pairs_alternate_and_export_true_fake_statistics(tmp_path):
    provider = FakeProvider()
    report = run_offline(compare(provider, output_dir=tmp_path))
    assert len(report.get("pairs", [])) == 27
    assert len(provider.calls) == 54
    assert [c[0] for c in provider.calls[:4]] == ["baseline", "pipeline", "pipeline", "baseline"]
    assert provider.calls[0][1] == provider.calls[1][1]
    assert provider.stores[0] is not provider.stores[1]
    assert report["provenance"] == ["fake_provider"]
    assert report["label_status"] == "author_known_regression"
    assert report["human_review_performed"] is False
    assert report["independent_benchmark"] is False
    assert report["metadata"] == provider.metadata
    assert report["summary"]["baseline"]["sample_count"] == 27
    assert report["summary"]["baseline"]["completed"] == 27
    assert report["summary"]["baseline"]["estimated_cost_usd"] == "0.027"
    assert report["summary"]["baseline"]["workflow_ms"] == {
        "sample_count": 27,
        "median": 28.0,
        "p95": 52.0,
        "quantile_method": "nearest_rank_ceiling",
    }
    assert report["summary"]["by_language"]["pt"]["pipeline"]["sample_count"] == 9
    assert all(len(v) == 64 for v in report["hashes"].values())
    exported = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    assert exported == report
    assert "fake_provider" in (tmp_path / "comparison.md").read_text(encoding="utf-8")


def test_failures_keep_both_results_and_partial_pairs_without_secret_errors(tmp_path):
    provider = FakeProvider(failure_at=2)
    report = run_offline(compare(provider, output_dir=tmp_path, repeats=1))
    assert len(report.get("pairs", [])) == 9
    assert report["pairs"][0]["baseline"]["result"]["status"] == "completed"
    assert report["pairs"][0]["pipeline"]["result"]["status"] == "failed"
    assert report["summary"]["pipeline"]["completed"] == 0
    assert "sensitive details" not in json.dumps(report)
    assert report["summary"]["pipeline"]["estimated_cost_usd"] is None


def test_cancellation_before_calls_retains_all_pairs_and_unmeasured_metrics(tmp_path):
    provider = FakeProvider()
    report = run_offline(compare(provider, output_dir=tmp_path, cancelled=lambda: True))
    assert len(report.get("pairs", [])) == 27
    assert provider.calls == []
    assert report["status"] == "cancelled"
    assert report["summary"]["baseline"]["attempted"] == 0
    assert report["summary"]["baseline"]["estimated_cost_usd"] is None
    assert report["summary"]["baseline"]["workflow_ms"]["median"] is None
    assert all(p["pipeline"]["result"]["status"] == "cancelled" for p in report["pairs"])


@pytest.mark.parametrize(
    "unknown_at,cost,cap,expected_calls", [(1, "0.001", "1", 1), (None, "0.01", "0.02", 2)]
)
def test_budget_is_overall_not_per_case_and_unknown_cost_stops(
    tmp_path, unknown_at, cost, cap, expected_calls
):
    provider = FakeProvider(unknown_at=unknown_at, cost=cost)
    report = run_offline(compare(provider, output_dir=tmp_path, max_cost_usd=Decimal(cap)))
    assert len(report.get("pairs", [])) == 27
    assert len(provider.calls) == expected_calls
    assert report["status"] == "budget_exceeded"
    assert provider.calls[-1][2]["max_cost_usd"] <= Decimal(cap)
    assert report["pairs"][-1]["pipeline"]["result"]["status"] == "budget_exceeded"


@pytest.mark.parametrize("repeats,cap", [(0, "1"), (True, "1"), (1, "0"), (1, "NaN"), (1, "-1")])
def test_invalid_run_limits_fail_before_provider_calls(tmp_path, repeats, cap):
    provider = FakeProvider()
    with pytest.raises(ValueError):
        run_offline(
            compare(provider, output_dir=tmp_path, repeats=repeats, max_cost_usd=Decimal(cap))
        )
    assert provider.calls == []


def test_session_remaining_caps_first_call_and_pairs_have_matching_statistics(tmp_path):
    class Session:
        def summary(self):
            return {"remaining_usd": "0.002", "blocked": False, "unknown_cost": False}

    provider = FakeProvider(cost="0.001")
    provider.session = Session()
    report = run_offline(compare(provider, output_dir=tmp_path, repeats=1))
    assert provider.calls[0][2]["max_cost_usd"] == Decimal("0.002")
    assert report["summary"]["paired"]["complete_pairs"] == 9
    assert (
        report["summary"]["paired"]["workflow_ms_delta_pipeline_minus_baseline"]["sample_count"]
        == 9
    )
    assert report["summary"]["paired"]["estimated_cost_delta_usd"] == "0.000"


def test_cancellation_between_pair_members_preserves_partial_pair(tmp_path):
    provider = FakeProvider()
    report = run_offline(
        compare(provider, output_dir=tmp_path, repeats=1, cancelled=lambda: len(provider.calls) > 0)
    )
    assert len(provider.calls) == 1
    assert report["pairs"][0]["baseline"]["result"]["status"] == "completed"
    assert report["pairs"][0]["pipeline"]["result"]["status"] == "cancelled"
    assert report["summary"]["paired"]["complete_pairs"] == 0
    assert (
        report["summary"]["paired"]["workflow_ms_delta_pipeline_minus_baseline"]["sample_count"]
        == 0
    )


def test_exact_final_cost_cap_does_not_relabel_complete_comparison(tmp_path):
    provider = FakeProvider(cost="0.01")
    report = run_offline(
        compare(provider, output_dir=tmp_path, repeats=1, max_cost_usd=Decimal("0.18"))
    )
    assert report["status"] == "completed"
    assert report["complete_pairs"] == 9


def test_optional_recording_forwards_both_arms_without_path_or_authentic_claim(tmp_path):
    provider = FakeProvider()
    recording = tmp_path / "private-record-location"
    report = run_offline(compare(provider, output_dir=tmp_path, repeats=1, record_dir=recording))
    assert all(call[2]["record_dir"] == recording for call in provider.calls)
    assert report["recording_requested"] is True
    assert report["provenance"] == ["fake_provider"]
    assert str(recording) not in json.dumps(report)


def test_blocked_session_prevents_every_call_without_inventing_measurements(tmp_path):
    class Session:
        def summary(self):
            return {"remaining_usd": "0.5", "blocked": True, "unknown_cost": True}

    provider = FakeProvider()
    provider.session = Session()
    report = run_offline(compare(provider, output_dir=tmp_path, repeats=1))
    assert provider.calls == []
    assert report["status"] == "budget_exceeded"
    assert report["summary"]["baseline"]["estimated_cost_usd"] is None
    assert len(report["pairs"]) == 9
