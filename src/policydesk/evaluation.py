"""Author-known synthetic regression harness. No model-quality inference."""

import hashlib
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .fixtures import cases, check_reserved_hash, orders, ticket_for
from .models import TODAY, Decision, DraftReply
from .openai_client import ReplayClient
from .pipeline import run
from .resources import DATA, canonical, digest
from .store import Store
from .validators import check


def source_hash() -> str:
    package = Path(__file__).parent
    files = sorted(
        [
            *package.glob("*.py"),
            *DATA.rglob("*.yaml"),
            *DATA.rglob("*.json"),
            *DATA.rglob("*.jsonl"),
            *DATA.rglob("*.sha256"),
        ]
    )
    return digest(
        {
            p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        }
    )


def evaluate_split(split: str, output_dir: Path) -> dict[str, Any]:
    dataset = cases(split)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="synthetic-", dir=output_dir) as temporary:
        for case in dataset:
            store = Store(Path(temporary) / f"{case['id']}.sqlite")
            try:
                store.seed(orders())
                result = run(ticket_for(case), store, ReplayClient(), TODAY)
                expected = case["expected"]
                actual = {key: result["decision"][key] for key in expected}
                oracle = Decision.model_validate({**expected, "reasons": ["authored_label"]})
                unsafe = check(DraftReply.model_validate(result["reply"]), oracle, case["lang"])
                rows.append(
                    {
                        "id": case["id"],
                        "language": case["lang"],
                        "tags": case["tags"],
                        "passed": actual == expected and not unsafe,
                        "expected": expected,
                        "actual": actual,
                        "unsafe_codes": [v.code for v in unsafe],
                        "result": result,
                    }
                )
            finally:
                store.close()
    failures = sum(not row["passed"] for row in rows)
    report = {
        "schema_version": 1,
        "evaluation_kind": "synthetic_regression",
        "provenance": "synthetic",
        "split": split,
        "frozen_date": TODAY.isoformat(),
        "source_sha256": source_hash(),
        "reserved_sha256": check_reserved_hash(),
        "label_sources": dict(Counter(c["label_source"] for c in dataset)),
        "human_review_performed": False,
        "total": len(rows),
        "failed": failures,
        "metrics": {
            "outcomes": dict(Counter(row["actual"]["outcome"] for row in rows)),
            "unsafe_replies_detected": sum(bool(row["unsafe_codes"]) for row in rows),
            "repair_attempts": sum(row["result"]["repair_attempted"] for row in rows),
            "api_cost_usd": None,
            "model_latency_ms": None,
            "cached_input_share": None,
            "baseline": None,
        },
        "cases": rows,
    }
    (output_dir / f"{split}.json").write_text(
        canonical(report) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        f"# {split}: synthetic regression",
        "",
        "Author-known synthetic responses; not API recordings or a model benchmark.",
        "",
        f"Command: `policydesk eval --split {split}`",
        f"Frozen date: {TODAY}",
        f"Source SHA-256: `{report['source_sha256']}`",
        f"Reserved SHA-256: `{report['reserved_sha256']}`",
        "",
        f"Cases: {len(rows)}; failed: {failures}; unsafe replies detected by these checks: {report['metrics']['unsafe_replies_detected']}.",
        "Labels: agent_drafted. Human review: not performed.",
        "API cost, model latency, caching and real baseline comparison: unmeasured/unavailable.",
        "",
        "| Case | Outcome | Result |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {r['id']} | {r['actual']['outcome']} | {'PASS' if r['passed'] else 'FAIL'} |"
        for r in rows
    )
    (output_dir / f"{split}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {
        "total": len(rows),
        "failed": failures,
        "provenance": "synthetic",
        "report": str(output_dir / f"{split}.json"),
    }
