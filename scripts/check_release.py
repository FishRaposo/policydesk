"""Fail-closed public-copy readiness check; does not publish anything."""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def issues(root: Path) -> list[str]:
    failures: list[str] = []
    try:
        approval = json.loads((root / "config/publication.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        approval = {}
    if approval.get("status") != "finalized" or approval.get("reviewed_by") != "Claude":
        failures.append(
            "Claude-finalized public copy is pending; do not publish, tag, deploy or change portfolio claims"
        )
    if not approval.get("repository_description"):
        failures.append("Approved repository description is missing")
    for name in ("README.md", "docs/CASE_STUDY.md"):
        path = root / name
        if not path.is_file():
            failures.append(f"Finalized {name} is missing")
            continue
        if re.search(r"FILL:|TODO|\[FISH", path.read_text(encoding="utf-8")):
            failures.append(f"Unresolved publication marker in {name}")
        if (
            approval.get("finalized_files", {}).get(name)
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            failures.append(f"Claude-finalized SHA-256 missing or stale for {name}")
    for name in (
        "LICENSE",
        "uv.lock",
        "web/package-lock.json",
        "reports/dev.json",
        "reports/heldout.json",
        "docs/media/policydesk-proof.gif",
    ):
        if not (root / name).is_file():
            failures.append(f"Release artifact missing: {name}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--status", action="store_true", help="Report readiness for CI; pending is not a deployment"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    failures = issues(args.root)
    print(f"ready={'false' if failures else 'true'}")
    for failure in failures:
        print(f"- {failure}")
    raise SystemExit(0 if args.status or not failures else 1)


if __name__ == "__main__":
    main()
