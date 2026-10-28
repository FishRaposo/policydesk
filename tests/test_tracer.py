"""Catch a broken install, CLI wiring, or an incorrect end-to-end refund."""
import json
import subprocess
import sys


def test_cli_demo_executes_pipeline(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "policydesk.cli", "demo", "--db", str(tmp_path / "demo.db")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["provenance"] == "synthetic"
    assert report["decision"]["outcome"] == "approve"
    assert report["decision"]["actions"][0]["amount"] == "94.80"
    assert report["pending_actions"]
    assert report["violations"] == []
