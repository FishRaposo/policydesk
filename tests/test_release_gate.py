"""Publication must fail closed while Claude-owned copy is unfinished."""

import hashlib
import json
import subprocess
import sys


def test_publication_gate_rejects_unfinalized_copy(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    assert "Claude" in result.stdout


def test_ci_readiness_can_report_pending_without_deploying(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py", "--status", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "ready=false" in result.stdout


def test_explicit_owner_override_can_finalize_copy_without_claiming_claude_review(tmp_path):
    required = [
        "README.md",
        "docs/CASE_STUDY.md",
        "LICENSE",
        "uv.lock",
        "web/package-lock.json",
        "reports/dev.json",
        "reports/heldout.json",
        "docs/media/policydesk-proof.gif",
    ]
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic test fixture\n", encoding="utf-8")
    record = {
        "status": "finalized",
        "reviewed_by": "owner_override",
        "repository_description": "Synthetic test fixture",
        "finalized_files": {
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
            for name in required[:2]
        },
        "authorization": {
            "type": "direct_user_instruction",
            "date": "2026-10-28",
            "quote": "No, just roll with the current one",
        },
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config/publication.json").write_text(json.dumps(record), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout
    assert "ready=true" in result.stdout
    record["authorization"]["quote"] = ""
    (tmp_path / "config/publication.json").write_text(json.dumps(record), encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, "scripts/check_release.py", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert rejected.returncode == 1
