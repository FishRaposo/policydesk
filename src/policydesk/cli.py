"""Offline default; recruiter-initiated local live requests require explicit consent."""

import asyncio
import getpass
import json
import os
import sys
import warnings
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal

import typer

from .fixtures import cases, orders, ticket_for
from .models import TODAY, Language, Ticket
from .openai_client import ReplayClient
from .pipeline import run as run_pipeline
from .store import Store

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
DB = Path(".runtime/policydesk.sqlite")
DbOption = Annotated[Path, typer.Option(help="Local SQLite path (simulated actions only)")]


def output(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def today() -> date:
    return date.fromisoformat(os.environ.get("POLICYDESK_TODAY", TODAY.isoformat()))


def execute(ticket: Ticket, db: Path) -> None:
    client = ReplayClient()
    store = Store(db)
    try:
        store.seed(orders())
        output(run_pipeline(ticket, store, client, today()))
    finally:
        store.close()


@app.command()
def init(db: DbOption = DB) -> None:
    """Initialize fictional orders in a local database."""
    store = Store(db)
    try:
        store.seed(orders())
        output({"db": str(db), "provenance": "synthetic", "executed": False})
    finally:
        store.close()


@app.command()
def demo(
    case: Annotated[str, typer.Option(help="Dev scenario ID")] = "D-PT-01", db: DbOption = DB
) -> None:
    """Run a committed synthetic dev ticket through the Python pipeline."""
    match = next((c for c in cases() if c["id"] == case), None)
    if match is None:
        raise typer.BadParameter("Unknown dev case; choose list-cases")
    execute(ticket_for(match), db)


@app.command()
def list_cases() -> None:
    """List available development replay inputs."""
    output(
        [{key: c[key] for key in ("id", "lang", "customer_id", "message", "tags")} for c in cases()]
    )


@app.command()
def run(
    message: str,
    customer: Annotated[str, typer.Option()],
    language: Annotated[Language, typer.Option()] = "pt",
    db: DbOption = DB,
    mode: Annotated[Literal["replay", "live"], typer.Option()] = "replay",
    model: Annotated[Literal["gpt-6-luna", "gpt-6.1-terra"], typer.Option()] = "gpt-6-luna",
    confirm_spend: Annotated[
        bool, typer.Option(help="Explicitly allow requests billed to your own API key")
    ] = False,
    max_cost_usd: Annotated[
        str, typer.Option(help="Application estimate guard, not a billing guarantee")
    ] = "0.05",
    session_limit_usd: Annotated[str, typer.Option()] = "1.00",
    record: Annotated[
        bool, typer.Option(help="Opt in to credential-free provider capture under .runtime")
    ] = False,
    output_dir: Annotated[Path, typer.Option()] = Path(".runtime/runs"),
) -> None:
    """Replay a known input, or explicitly initiate a recruiter-funded live ticket."""
    ticket = Ticket(message=message, customer_id=customer, language=language)
    if mode == "replay":
        if record:
            raise typer.BadParameter("--record requires --mode live --confirm-spend")
        execute(ticket, db)
        return
    require_consent(confirm_spend)
    cap, session_cap = allowance(max_cost_usd), allowance(session_limit_usd)
    key = read_key()

    async def invoke():
        from .live import OpenAIProvider
        from .telemetry import SessionBudget

        provider = OpenAIProvider(key, SessionBudget(session_cap), model=model)
        store = Store(db)
        try:
            store.seed(orders())
            return await provider.run(
                ticket,
                store,
                today=TODAY,
                max_cost_usd=cap,
                record_dir=Path(".runtime/recordings") if record else None,
            )
        finally:
            store.close()
            await provider.aclose()

    result = invoke_live(invoke)
    write_run(result, output_dir)
    output(result)
    if result.get("status") != "completed":
        raise typer.Exit(1)


def require_consent(confirmed: bool) -> None:
    if not confirmed:
        raise typer.BadParameter("Live requests require --confirm-spend; they use your API billing")


def allowance(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise typer.BadParameter("USD allowance must be positive and finite") from exc
    if not amount.is_finite() or amount <= 0:
        raise typer.BadParameter("USD allowance must be positive and finite")
    return amount


def read_key() -> str:
    """Only called by explicitly enabled local live commands, never by replay/help."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        if not sys.stdin.isatty():
            raise typer.BadParameter(
                "Use an interactive terminal for hidden key entry, or set OPENAI_API_KEY locally"
            )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("Your OpenAI API key (hidden, memory only): ")
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt) as exc:
            raise typer.BadParameter("Hidden key input unavailable; no key was accepted") from exc
    key = key.strip()
    if not key or any(c.isspace() for c in key):
        raise typer.BadParameter("Supply a nonempty API key without whitespace")
    return key


def invoke_live(operation):
    try:
        return asyncio.run(operation())
    except ImportError as exc:
        raise typer.BadParameter("Install the optional live extra: uv sync --extra live") from exc
    except Exception:
        typer.echo(
            "Local live run failed; credentials and HTTP details are not displayed", err=True
        )
        raise typer.Exit(1) from None


def write_run(result: dict, directory: Path) -> None:
    from .resources import canonical

    directory.mkdir(parents=True, exist_ok=True)
    name = result["run_id"]
    (directory / f"{name}.json").write_text(
        canonical(result) + "\n", encoding="utf-8", newline="\n"
    )
    (directory / f"{name}.md").write_text(
        "# PolicyDesk local run\n\nFictional data. Estimated costs are not invoice totals.\n\n```json\n"
        + json.dumps(result, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
        newline="\n",
    )


@app.command()
def serve(
    enable_live: Annotated[
        bool,
        typer.Option(
            help="Enable explicit recruiter-funded requests; startup makes no API request"
        ),
    ] = False,
    open_browser: Annotated[bool, typer.Option(help="Open the loopback workspace")] = False,
) -> None:
    """Serve the packaged browser on loopback; key entry is terminal-only."""
    try:
        import uvicorn

        from .server import ORIGIN, VERIFICATION, create_app
    except ImportError as exc:
        raise typer.BadParameter("Install the optional live extra: uv sync --extra live") from exc
    web = Path(__file__).parent / "web_dist"
    if not (web / "index.html").is_file():
        development = Path(__file__).resolve().parents[2] / "web/dist"
        if not (development / "index.html").is_file():
            raise typer.BadParameter(
                "Frontend missing: install the release wheel, or build web and run scripts/package_web.py"
            )
        web = development
    key = read_key() if enable_live else None
    application = create_app(key, data_dir=Path(".runtime/local"), web_dir=web)
    typer.echo(VERIFICATION)
    typer.echo(f"Local workspace: {ORIGIN}/policydesk/ — startup makes no OpenAI request")
    typer.echo(
        "Live controls enabled; each run requires explicit consent"
        if enable_live
        else "Live mode disabled"
    )
    if open_browser:
        import webbrowser

        webbrowser.open(f"{ORIGIN}/policydesk/")
    uvicorn.run(application, host="127.0.0.1", port=8765, access_log=False, log_level="warning")


@app.command()
def benchmark(
    compare: Annotated[
        bool, typer.Option(help="Run the guarded pipeline against a single-call baseline")
    ] = False,
    confirm_spend: Annotated[bool, typer.Option()] = False,
    model: Annotated[Literal["gpt-6-luna", "gpt-6.1-terra"], typer.Option()] = "gpt-6-luna",
    max_cost_usd: Annotated[str, typer.Option()] = "1.00",
    repeats: Annotated[int, typer.Option(min=1, max=10)] = 3,
    record: Annotated[bool, typer.Option()] = False,
    output_dir: Annotated[Path, typer.Option()] = Path(".runtime/comparisons"),
) -> None:
    """Explicitly funded paired comparison on nine author-known development cases."""
    require_consent(confirm_spend)
    if not compare:
        raise typer.BadParameter("Select --compare to run both declared systems")
    cap, key = allowance(max_cost_usd), read_key()

    async def invoke():
        from .benchmark import compare as run_comparison
        from .live import OpenAIProvider
        from .telemetry import SessionBudget

        provider = OpenAIProvider(key, SessionBudget(cap), model=model)
        try:
            return await run_comparison(
                provider,
                output_dir=output_dir,
                repeats=repeats,
                max_cost_usd=cap,
                record_dir=Path(".runtime/recordings") if record else None,
            )
        finally:
            await provider.aclose()

    result = invoke_live(invoke)
    output(result)
    if result.get("status") not in ("completed", "complete"):
        raise typer.Exit(1)


@app.command(name="replay-recording")
def replay_recording(path: Path) -> None:
    """Read an integrity-checked recording; never request a key or contact a provider."""
    from .live import replay_recording as replay

    output(replay(path))


@app.command()
def approve(
    action_id: str, actor: Annotated[str, typer.Option()] = "demo-operator", db: DbOption = DB
) -> None:
    """Record local authorization only; executes no external action."""
    store = Store(db)
    try:
        output(store.approve(action_id, actor, today()))
    finally:
        store.close()


@app.command()
def report(db: DbOption = DB) -> None:
    """Read the local audit history."""
    store = Store(db)
    try:
        output(store.history())
    finally:
        store.close()


@app.command(name="eval")
def evaluate(
    split: Annotated[str, typer.Option()] = "heldout",
    baseline: Annotated[bool, typer.Option()] = False,
    output_dir: Annotated[Path, typer.Option()] = Path(".runtime/reports"),
) -> None:
    """Run synthetic regression cases, not a model benchmark."""
    if baseline:
        raise typer.BadParameter(
            "Real-model baseline comparison is unavailable in this synthetic prototype"
        )
    from .evaluation import evaluate_split

    result = evaluate_split(split, output_dir)
    output(result)
    if result["failed"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
