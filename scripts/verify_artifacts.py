"""Regenerate source-bound exports/reports in scratch and compare exact bytes."""

import argparse
import tempfile
from pathlib import Path

from export_web import export

from policydesk.evaluation import evaluate_split

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Explicitly update derived references, never cases/cassettes",
    )
    args = parser.parse_args()
    if args.write:
        for split in ("dev", "heldout"):
            result = evaluate_split(split, ROOT / "reports")
            if result["failed"]:
                raise SystemExit(f"Cannot accept failing {split} report")
        export(ROOT / "web/src/generated")
        return
    with tempfile.TemporaryDirectory(prefix="policydesk-artifacts-") as temporary:
        scratch = Path(temporary)
        for split in ("dev", "heldout"):
            if evaluate_split(split, scratch / "reports")["failed"]:
                raise SystemExit(f"Synthetic regression failed: {split}")
        export(scratch / "generated")
        for name in ("dev.json", "dev.md", "heldout.json", "heldout.md"):
            if (scratch / "reports" / name).read_bytes() != (ROOT / "reports" / name).read_bytes():
                raise SystemExit(f"Report is stale or irreproducible: {name}")
        for name in ("bundle.json", "parity.json"):
            if (scratch / "generated" / name).read_bytes() != (
                ROOT / "web/src/generated" / name
            ).read_bytes():
                raise SystemExit(f"Browser export is stale: {name}")
    print("All synthetic reports and browser exports reproduce byte-for-byte")


if __name__ == "__main__":
    main()
