"""Publication must fail closed while Claude-owned copy is unfinished."""

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
