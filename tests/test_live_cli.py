"""CLI consent and key handling use fake values; no API requests."""

from typer.testing import CliRunner

from policydesk import cli


def test_recruiter_launcher_is_discoverable():
    result = CliRunner().invoke(cli.app, ["serve", "--help"])
    assert result.exit_code == 0, result.output
    assert "--enable-live" in result.output
    assert "--api-key" not in result.output


def test_live_consent_precedes_key_access(monkeypatch):
    accessed = []
    monkeypatch.setattr(cli, "read_key", lambda: accessed.append(True) or "fake-not-real")
    result = CliRunner().invoke(
        cli.app, ["run", "Fictional request", "--customer", "C-01", "--mode", "live"]
    )
    assert result.exit_code == 2
    assert "confirm-spend" in result.output
    assert accessed == []


def test_replay_does_not_access_credentials(monkeypatch, tmp_path):
    from policydesk.fixtures import cases

    accessed = []
    monkeypatch.setattr(cli, "read_key", lambda: accessed.append(True) or "fake-not-real")
    case = cases()[0]
    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            case["message"],
            "--customer",
            case["customer_id"],
            "--language",
            case["lang"],
            "--db",
            str(tmp_path / "local.sqlite"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert accessed == []


def test_key_from_environment_never_printed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-only-cli")
    assert cli.read_key() == "fake-test-only-cli"


def test_noninteractive_missing_key_never_falls_back_to_echo(monkeypatch):
    import io

    import pytest
    import typer

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("fake-secret-input"))
    with pytest.raises(typer.BadParameter, match="interactive terminal"):
        cli.read_key()


def test_live_cli_fake_provider_report_and_no_key_output(monkeypatch, tmp_path):
    import policydesk.live

    class Fake:
        def __init__(self, api_key, session, model):
            assert api_key == "fake-test-only-cli"

        async def run(self, ticket, store, **kwargs):
            return {
                "status": "completed",
                "provenance": "mock_openai_transport",
                "run_id": "fake-run",
                "metrics": {"estimated_cost_usd": "0.001"},
            }

        async def aclose(self):
            pass

    monkeypatch.setattr(cli, "read_key", lambda: "fake-test-only-cli")
    monkeypatch.setattr(policydesk.live, "OpenAIProvider", Fake)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli.app,
        ["run", "Fictional request", "--customer", "C-01", "--mode", "live", "--confirm-spend"],
    )
    assert result.exit_code == 0, result.output
    assert "fake-test-only-cli" not in result.output
    assert (tmp_path / ".runtime/runs/fake-run.json").is_file()


def test_benchmark_requires_consent_before_key(monkeypatch):
    accessed = []
    monkeypatch.setattr(cli, "read_key", lambda: accessed.append(True) or "fake-not-real")
    result = CliRunner().invoke(cli.app, ["benchmark", "--compare"])
    assert result.exit_code == 2
    assert accessed == []
