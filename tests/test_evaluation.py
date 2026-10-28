"""Catch universal handoff, mutated reserved data and irreproducible reports."""

import json
import subprocess
import sys


def test_cli_evaluation_produces_reproducible_synthetic_report(tmp_path):
    command = [
        sys.executable,
        "-m",
        "policydesk.cli",
        "eval",
        "--split",
        "heldout",
        "--output-dir",
        str(tmp_path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    assert result["total"] == 36 and result["failed"] == 0
    report_path = tmp_path / "heldout.json"
    original = report_path.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert second.returncode == 0, second.stderr
    assert report_path.read_bytes() == original
    report = json.loads(original)
    assert report["evaluation_kind"] == "synthetic_regression"
    assert report["metrics"]["api_cost_usd"] is None
    assert report["metrics"]["model_latency_ms"] is None
    assert report["metrics"]["baseline"] is None
    assert report["metrics"]["outcomes"]["approve"] == 18
    assert report["metrics"]["outcomes"]["deny"] == 6
    assert report["metrics"]["outcomes"]["needs_human"] == 12
    assert report["label_sources"] == {"agent_drafted": 36}


def test_baseline_command_is_explicitly_unavailable(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "policydesk.cli",
            "eval",
            "--baseline",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "unavailable" in result.stderr
    assert not (tmp_path / "heldout.json").exists()
