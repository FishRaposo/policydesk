"""Paired recruiter demonstration; author-known development cases only."""

import asyncio
import hashlib
import json
import math
import tempfile
from collections import Counter
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

from pydantic import ValidationError

from .fixtures import cases, orders, ticket_for
from .models import TODAY, Decision, DraftReply, Extraction
from .resources import DATA, canonical, digest
from .store import Store
from .validators import check


def recruiter_cases() -> list[dict[str, Any]]:
    """Select the first unfaulted dev label in each language/outcome stratum."""
    development = sorted(cases("dev"), key=lambda case: case["id"])
    return [
        next(
            case
            for case in development
            if case["lang"] == language
            and case["expected"]["outcome"] == outcome
            and case.get("fault") is None
        )
        for language in ("pt", "es", "en")
        for outcome in ("approve", "deny", "needs_human")
    ]


def grade(result: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Apply the same independent gold oracle to either system's final result.

    Phrase, amount and language validators are bounded checks, not a semantic
    safety guarantee. Provider-reported violations are not used as the oracle.
    """
    gold = Decision.model_validate({**case["expected"], "reasons": ["authored_label"]})
    actual = result.get("decision")
    outcome_correct = actions_correct = clauses_correct = False
    try:
        decision = Decision.model_validate(actual)
        outcome_correct = decision.outcome == gold.outcome
        actions_correct = decision.actions == gold.actions
        clauses_correct = sorted(decision.clause_ids) == sorted(gold.clause_ids)
    except (ValidationError, TypeError, ValueError):
        pass
    reply_present = result.get("reply") is not None
    unsafe_codes: list[str] = []
    if reply_present:
        try:
            unsafe_codes = [
                violation.code
                for violation in check(
                    DraftReply.model_validate(result["reply"]), gold, case["lang"]
                )
            ]
        except (ValidationError, TypeError, ValueError):
            unsafe_codes = ["reply_schema_invalid"]
    extraction_correct = None
    extraction_fields = None
    extraction_applicable = not (
        result.get("system") == "baseline" and result.get("extraction") is None
    )
    if case.get("extraction") is not None and extraction_applicable:
        expected_extraction = Extraction.model_validate(case["extraction"])
        try:
            extraction = Extraction.model_validate(result.get("extraction"))
            extraction_fields = {
                name: getattr(extraction, name) == getattr(expected_extraction, name)
                for name in Extraction.model_fields
            }
            extraction_correct = all(extraction_fields.values())
        except (ValidationError, TypeError, ValueError):
            extraction_correct = False
    completed = result.get("status") == "completed"
    primary_pass = (
        completed
        and outcome_correct
        and actions_correct
        and clauses_correct
        and reply_present
        and not unsafe_codes
    )
    return {
        "passed": primary_pass,
        "primary_pass": primary_pass,
        "outcome_correct": outcome_correct,
        "actions_correct": actions_correct,
        "clauses_correct": clauses_correct,
        "extraction_correct": extraction_correct,
        "extraction_fields": extraction_fields,
        "reply_assessed": reply_present,
        "unsafe_codes": unsafe_codes,
    }


def _cost(result: dict[str, Any]) -> Decimal | None:
    metrics = result.get("metrics") or {}
    raw = metrics.get("estimated_cost_usd")
    if metrics.get("unknown_cost") or not isinstance(raw, str):
        return None
    try:
        value = Decimal(raw)
        return value if value.is_finite() and value >= 0 else None
    except InvalidOperation:
        return None


def _distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "sample_count": len(ordered),
        "median": float(median(ordered)) if ordered else None,
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
        "quantile_method": "nearest_rank_ceiling",
    }


def _summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = [entry for entry in entries if entry["attempted"]]
    costs = [_cost(entry["result"]) for entry in attempted]
    known = [value for value in costs if value is not None]
    complete_cost = bool(attempted) and len(known) == len(costs)
    summary: dict[str, Any] = {
        "sample_count": len(entries),
        "attempted": len(attempted),
        "completed": sum(e["result"].get("status") == "completed" for e in entries),
        "passed": sum(e["grade"]["passed"] for e in entries),
        "failed": sum(not e["grade"]["passed"] for e in entries),
        "statuses": dict(Counter(e["result"].get("status") for e in entries)),
        "unsafe_replies_detected": sum(bool(e["grade"]["unsafe_codes"]) for e in entries),
        "replies_assessed": sum(e["grade"]["reply_assessed"] for e in entries),
        "repair_attempts": sum(bool(e["result"].get("repair_attempted")) for e in entries),
        "handoffs": sum(
            (e["result"].get("decision") or {}).get("outcome") == "needs_human" for e in entries
        ),
        "extractions_assessed": sum(
            e["grade"]["extraction_correct"] is not None for e in attempted
        ),
        "extractions_correct": sum(e["grade"]["extraction_correct"] is True for e in attempted),
        "estimated_cost_usd": str(sum(known, Decimal(0))) if complete_cost else None,
        "known_cost_subtotal_usd": str(sum(known, Decimal(0))) if known else None,
        "cost_sample_count": len(known),
        "unknown_cost_count": len(costs) - len(known),
    }
    for metric in ("workflow_ms", "api_round_trip_ms", "local_processing_ms", "ttft_ms"):
        samples = [
            float(value)
            for entry in attempted
            if isinstance(value := (entry["result"].get("metrics") or {}).get(metric), (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        ]
        summary[metric] = _distribution(samples)
    return summary


def _unattempted(status: str, error_code: str) -> dict[str, Any]:
    return {
        "status": status,
        "error_code": error_code,
        "provenance": "not_executed",
        "decision": None,
        "reply": None,
        "extraction": None,
        "pending_actions": [],
        "repair_attempted": False,
        "calls": [],
        "metrics": None,
    }


def _paired_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        p
        for p in pairs
        if all(p[s]["result"].get("status") == "completed" for s in ("baseline", "pipeline"))
    ]
    cost_deltas = [
        pipeline - baseline
        for pair in pairs
        if pair["baseline"]["attempted"]
        and pair["pipeline"]["attempted"]
        and (baseline := _cost(pair["baseline"]["result"])) is not None
        and (pipeline := _cost(pair["pipeline"]["result"])) is not None
    ]
    summary: dict[str, Any] = {
        "planned_pairs": len(pairs),
        "complete_pairs": len(complete),
        "baseline_only_passed": sum(
            p["baseline"]["grade"]["passed"] and not p["pipeline"]["grade"]["passed"] for p in pairs
        ),
        "pipeline_only_passed": sum(
            p["pipeline"]["grade"]["passed"] and not p["baseline"]["grade"]["passed"] for p in pairs
        ),
        "both_passed": sum(
            p["pipeline"]["grade"]["passed"] and p["baseline"]["grade"]["passed"] for p in pairs
        ),
        "cost_delta_sample_count": len(cost_deltas),
        "estimated_cost_delta_usd": str(sum(cost_deltas, Decimal(0)))
        if pairs and len(cost_deltas) == len(pairs)
        else None,
    }
    for metric in ("workflow_ms", "api_round_trip_ms", "local_processing_ms", "ttft_ms"):
        deltas = []
        for pair in complete:
            values = [
                (pair[s]["result"].get("metrics") or {}).get(metric)
                for s in ("baseline", "pipeline")
            ]
            baseline, pipeline = values
            if (
                isinstance(baseline, (int, float))
                and not isinstance(baseline, bool)
                and isinstance(pipeline, (int, float))
                and not isinstance(pipeline, bool)
                and math.isfinite(baseline)
                and math.isfinite(pipeline)
                and baseline >= 0
                and pipeline >= 0
            ):
                deltas.append(float(pipeline) - float(baseline))
        summary[f"{metric}_delta_pipeline_minus_baseline"] = _distribution(deltas)
    return summary


def _hashes(selected: list[dict[str, Any]], snapshot: list[Any]) -> dict[str, str]:
    # Deliberately never traverses reserved fixtures or cassettes.
    package = Path(__file__).parent
    paths = [
        *package.glob("*.py"),
        DATA / "policy.yaml",
        DATA / "orders.yaml",
        DATA / "phrases.yaml",
        DATA / "cases/dev.jsonl",
    ]
    pricing = DATA / "model_pricing.json"
    if pricing.exists():
        paths.append(pricing)
    return {
        "source_sha256": digest(
            {
                path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(paths)
            }
        ),
        "policy_sha256": hashlib.sha256((DATA / "policy.yaml").read_bytes()).hexdigest(),
        "dev_cases_sha256": digest(selected),
        "orders_sha256": digest([order.model_dump(mode="json") for order in snapshot]),
    }


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    (output_dir / "comparison.json").write_text(canonical(report) + "\n", encoding="utf-8")
    lines = [
        "# Paired development comparison",
        "",
        "Label status: author_known_regression. Human review: not performed.",
        "This small authored dev set is not an independent benchmark. Bounded validators do not prove safety.",
        f"Execution provenance: {', '.join(report['provenance']) or 'not_executed'}.",
        f"Status: {report['status']}; planned pairs: {report['planned_pairs']}; complete pairs: {report['complete_pairs']}.",
        f"Frozen date: {report['frozen_date']}; repeats: {report['repeats']}.",
        "Latency p95 uses nearest rank (ceiling); missing observations remain null. Cost uses Decimal estimates.",
        "Primary pass requires completed status, exact gold outcome/actions/clauses and gold-based reply validators. Extraction accuracy is a separate diagnostic; baseline extraction is unmeasured.",
        "Repeats reuse cases and are not independent samples; no significance or generalization claim.",
        "",
        "## Model, settings and pricing",
        "",
        "```json",
        canonical(report["metadata"]),
        "```",
        "",
        "## Hashes",
        "",
        *[f"{key}: `{value}`" for key, value in report["hashes"].items()],
        "",
        "## Summary (overall and by language)",
        "",
        "```json",
        canonical(report["summary"]),
        "```",
        "",
        "| Case | Repeat | First | Baseline status / grade | Pipeline status / grade |",
        "|---|---|---|---|---|",
    ]
    for pair in report["pairs"]:
        cells = [
            f"{pair[system]['result']['status']} / {'PASS' if pair[system]['grade']['passed'] else 'FAIL'}"
            for system in ("baseline", "pipeline")
        ]
        lines.append(
            f"| {pair['case_id']} | {pair['repeat']} | {pair['order'][0]} | {cells[0]} | {cells[1]} |"
        )
    lines += [
        "",
        "Full results, failures and grades for both systems are preserved in comparison.json.",
    ]
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def compare(
    provider: Any,
    *,
    output_dir: Path,
    repeats: int = 3,
    max_cost_usd: Decimal = Decimal("1"),
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    record_dir: Path | None = None,
) -> dict[str, Any]:
    """Run sequential, counterbalanced pairs under one overall/session allowance.

    The provider supplies the same model/settings to both workflows. Baseline
    preloads the same authorized facts which pipeline reads using scoped tools.
    No pending actions are created. Calling this function can spend with a live
    provider; the caller owns explicit user initiation and the single-job lock.
    """
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    if not isinstance(max_cost_usd, Decimal) or not max_cost_usd.is_finite() or max_cost_usd <= 0:
        raise ValueError("max_cost_usd must be a finite positive Decimal")
    selected, snapshot = recruiter_cases(), orders()
    hashes = _hashes(selected, snapshot)
    metadata = json.loads(canonical(provider.benchmark_metadata()))
    # A JSON snapshot makes later provider mutation visible instead of rewriting metadata.
    metadata_hash = digest(metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    remaining = max_cost_usd
    stop: str | None = None
    pairs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="paired-", dir=output_dir) as temporary:
        for repeat in range(1, repeats + 1):
            for case in selected:
                index = len(pairs)
                order = ["baseline", "pipeline"] if index % 2 == 0 else ["pipeline", "baseline"]
                ticket = ticket_for(case)
                authorized = [o for o in snapshot if o.customer_id == ticket.customer_id]
                pair: dict[str, Any] = {
                    "case_id": case["id"],
                    "language": case["lang"],
                    "repeat": repeat,
                    "order": order,
                    "expected": case["expected"],
                    "authorized_orders_sha256": digest(
                        [o.model_dump(mode="json") for o in authorized]
                    ),
                }
                for system in order:
                    if stop is None and cancelled and cancelled():
                        stop = "cancelled"
                    allowance = remaining
                    session = getattr(provider, "session", None)
                    if stop is None and session is not None:
                        session_state = session.summary()
                        if session_state["blocked"] or session_state["unknown_cost"]:
                            stop = "budget_exceeded"
                        allowance = min(allowance, Decimal(session_state["remaining_usd"]))
                    if stop is None and allowance <= 0:
                        stop = "budget_exceeded"
                    if stop is None and (
                        hashlib.sha256((DATA / "policy.yaml").read_bytes()).hexdigest()
                        != hashes["policy_sha256"]
                        or digest(provider.benchmark_metadata()) != metadata_hash
                    ):
                        stop = "failed"
                    attempted = stop is None
                    if not attempted:
                        result = _unattempted(stop or "failed", "comparison_stopped")
                    else:
                        store = Store(Path(temporary) / f"{index}-{system}.sqlite")
                        try:
                            store.seed(authorized)
                            if progress:
                                progress(
                                    {
                                        "phase": "comparison",
                                        "pair": index + 1,
                                        "planned_pairs": len(selected) * repeats,
                                        "system": system,
                                    }
                                )
                            method = provider.baseline if system == "baseline" else provider.run
                            result = await method(
                                ticket,
                                store,
                                today=TODAY,
                                max_cost_usd=allowance,
                                cancelled=cancelled,
                                progress=progress,
                                create_actions=False,
                                **({"record_dir": record_dir} if record_dir is not None else {}),
                            )
                        except asyncio.CancelledError:
                            result = _unattempted("cancelled", "comparison_cancelled")
                            result["provenance"] = "provider_exception"
                        except Exception:
                            # Never persist raw exception text; it could include request secrets.
                            result = _unattempted("failed", "provider_exception")
                            result["provenance"] = "provider_exception"
                        finally:
                            store.close()
                        cost = _cost(result)
                        if cost is not None:
                            remaining -= cost
                        status = result.get("status")
                        if status == "cancelled":
                            stop = "cancelled"
                        elif status == "budget_exceeded" or cost is None:
                            stop = "budget_exceeded"
                    pair[system] = {
                        "attempted": attempted,
                        "result": result,
                        "grade": grade(result, case),
                    }
                pairs.append(pair)
    summary = {system: _summary([p[system] for p in pairs]) for system in ("baseline", "pipeline")}
    summary["paired"] = _paired_summary(pairs)
    summary["by_language"] = {
        language: {
            **{
                system: _summary([p[system] for p in pairs if p["language"] == language])
                for system in ("baseline", "pipeline")
            },
            "paired": _paired_summary([p for p in pairs if p["language"] == language]),
        }
        for language in ("pt", "es", "en")
    }
    complete_pairs = sum(
        all(p[s]["result"].get("status") == "completed" for s in ("baseline", "pipeline"))
        for p in pairs
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "primary_grade": "completed_exact_gold_outcome_actions_clauses_and_bounded_reply_validators",
        "evaluation_kind": "paired_development_comparison",
        "label_status": "author_known_regression",
        "human_review_performed": False,
        "independent_benchmark": False,
        "label_sources": dict(Counter(c["label_source"] for c in selected)),
        "provenance": sorted(
            {
                str(p[s]["result"].get("provenance", "unknown"))
                for p in pairs
                for s in ("baseline", "pipeline")
                if p[s]["attempted"]
            }
        ),
        "status": stop or ("completed" if complete_pairs == len(pairs) else "failed"),
        "frozen_date": TODAY.isoformat(),
        "repeats": repeats,
        "planned_pairs": len(pairs),
        "complete_pairs": complete_pairs,
        "max_cost_usd": str(max_cost_usd),
        "recording_requested": record_dir is not None,
        "metadata": metadata,
        "hashes": hashes,
        "summary": summary,
        "pairs": pairs,
    }
    _write_report(report, output_dir)
    return report
