"""Export single-source policy data and Python observations for browser parity."""

import argparse
import itertools
import json
import tempfile
from datetime import timedelta
from pathlib import Path

import yaml

from policydesk.fixtures import cases, orders, ticket_for
from policydesk.models import TODAY, Extraction, Order
from policydesk.openai_client import ReplayClient
from policydesk.pipeline import run
from policydesk.policy import evaluate
from policydesk.replies import TEXT
from policydesk.resources import DATA, load_policy
from policydesk.store import Store

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def export(output: Path) -> None:
    all_orders = orders()
    order_map = {o.order_id: o for o in all_orders}
    scenarios = []
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary) / "export.db")
        try:
            store.seed(all_orders)
            for case in cases("dev"):
                result = run(ticket_for(case), store, ReplayClient(), TODAY)
                scenarios.append(
                    {
                        "id": case["id"],
                        "language": case["lang"],
                        "tags": case["tags"],
                        "ticket": ticket_for(case).model_dump(mode="json"),
                        "extraction": case["extraction"],
                        "order": order_map[case["extraction"]["order_id"]].model_dump(mode="json"),
                        "reference": {
                            "decision": result["decision"],
                            "reply": result["reply"],
                            "trace": result["trace"],
                            "violations": result["violations"],
                            "repair_attempted": result["repair_attempted"],
                        },
                    }
                )
        finally:
            store.close()
    write_json(
        output / "bundle.json",
        {
            "schema_version": 1,
            "provenance": "synthetic",
            "policy": load_policy(),
            "templates": TEXT,
            "phrases": yaml.safe_load((DATA / "phrases.yaml").read_text(encoding="utf-8")),
            "scenarios": scenarios,
        },
    )

    # Cross-runtime observations complement, rather than replace, independently
    # authored literal expectations in tests/test_policy.py and web/tests/policy.test.ts.
    observations = []
    for currency, limit in [("BRL", 40000), ("MXN", 150000), ("USD", 8000)]:
        for claim, age, delta in itertools.product(
            ["changed_mind", "damaged", "wrong_item"], [0, 7, 8, 30, 31], [-1, 0, 1]
        ):
            order = Order.model_validate(
                {
                    "order_id": "GN-DIFF",
                    "customer_id": "C-DIFF",
                    "currency": currency,
                    "items": [
                        {"name": "Fictional coffee", "price": f"{(limit + delta) / 100:.2f}"}
                    ],
                    "shipping_fee": "0.00",
                    "status": "delivered",
                    "shipped_at": "2026-09-01",
                    "estimated_delivery": "2026-09-10",
                    "delivered_at": (TODAY - timedelta(days=age)).isoformat(),
                    "carrier_status": "delivered",
                    "subscription_id": None,
                }
            )
            extraction = Extraction.model_validate(
                {
                    "language": "en",
                    "intent": "refund_request",
                    "order_id": order.order_id,
                    "claim": claim,
                    "customer_stated_amount": None,
                }
            )
            for customer in ("C-DIFF", "C-OTHER"):
                observations.append(
                    {
                        "order": order.model_dump(mode="json"),
                        "extraction": extraction.model_dump(mode="json"),
                        "customer_id": customer,
                        "expected": evaluate(extraction, order, customer, TODAY).model_dump(
                            mode="json"
                        ),
                    }
                )
    for scenario in scenarios:
        e = Extraction.model_validate(scenario["extraction"])
        o = Order.model_validate(scenario["order"])
        observations.append(
            {
                "order": o.model_dump(mode="json"),
                "extraction": e.model_dump(mode="json"),
                "customer_id": scenario["ticket"]["customer_id"],
                "expected": evaluate(e, o, scenario["ticket"]["customer_id"], TODAY).model_dump(
                    mode="json"
                ),
            }
        )
    write_json(output / "parity.json", observations)
    print(
        f"Exported {len(scenarios)} synthetic scenarios and {len(observations)} cross-runtime observations"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "web/src/generated")
    args = parser.parse_args()
    export(args.output)
